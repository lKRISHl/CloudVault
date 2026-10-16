"""Private durable preview lifecycle. PostgreSQL owns intents; S3 owns derivative bytes."""

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text, update

from app.core.config import settings
from app.models import FileVersion, PreviewJob, Tenant
from app.schemas.previews import PreviewJobRead, PreviewRead, PreviewRequest
from app.services.accounts import AccountService
from app.services.background_jobs import storage_namespace
from app.services.previews import PreviewService
from app.services.uploads import utc
from app.services.versions import VersionService
from app.storage.base import ObjectConflictError, ObjectNotFoundError, ObjectRef, StorageError

TTL = 900


def snapshot(row):
    return SimpleNamespace(
        **{column.name: getattr(row, column.name) for column in row.__table__.columns}
    )


class PreviewJobService:
    def __init__(self, db, storage=None, renderer=None):
        self.db, self.storage, self.renderer = db, storage, renderer

    async def lock_tenant(self, tenant_id):
        if self.db.bind.dialect.name == "sqlite":
            await self.db.execute(text("BEGIN IMMEDIATE"))
        await self.db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())

    async def authority(self, job):
        actor = SimpleNamespace(id=job.requested_by, tenant_id=job.tenant_id)
        versions = VersionService(self.db)
        file, _ = await versions.access(actor, job.file_id)
        version = await versions.find(actor, file, job.version_id)
        if (
            version.status != "uploaded"
            or job.generation
            and file.version_generation != job.generation
        ):
            raise HTTPException(409, "Preview source changed; request a new preview")
        if job.namespace != storage_namespace() or version.storage_bucket != job.storage_bucket:
            raise HTTPException(503, "Preview storage configuration changed")
        return actor, file, version

    async def enqueue(self, actor, file_id, payload, ip):
        await AccountService(self.db).limit(
            "preview-job", ip, str(actor.id), max_identity=100, max_ip=500
        )
        await self.lock_tenant(actor.tenant_id)
        versions = VersionService(self.db)
        file, _ = await versions.access(actor, file_id)
        version_id = payload.version_id or await self.db.scalar(
            select(FileVersion.id).where(
                FileVersion.file_id == file_id,
                FileVersion.tenant_id == actor.tenant_id,
                FileVersion.number == file.current_version,
            )
        )
        version = await versions.find(actor, file, version_id)
        if version.status != "uploaded":
            raise HTTPException(409, "Only completed versions can be previewed")
        if version.storage_bucket != settings.S3_BUCKET_NAME:
            raise HTTPException(503, "Preview storage configuration changed")
        generation = file.version_generation if payload.version_id is None else 0
        existing = await self.db.scalar(
            select(PreviewJob).where(
                PreviewJob.tenant_id == actor.tenant_id,
                PreviewJob.requested_by == actor.id,
                PreviewJob.request_id == payload.request_id,
            )
        )
        if existing:
            if (existing.file_id, existing.version_id, existing.page, existing.generation) != (
                file_id,
                version_id,
                payload.page,
                generation,
            ):
                raise HTTPException(409, "Preview request belongs to a different source")
            result = PreviewJobRead(
                id=existing.id, state=existing.state, expires_at=existing.expires_at
            )
            await self.db.commit()
            return result
        now = datetime.now(UTC)
        active = await self.db.scalar(
            select(func.count())
            .select_from(PreviewJob)
            .where(
                PreviewJob.tenant_id == actor.tenant_id,
                PreviewJob.expires_at > now,
                PreviewJob.state.in_(("queued", "running")),
            )
        )
        if active >= 20:
            raise HTTPException(429, "Workspace preview capacity busy; cancel or wait for expiry")
        job = PreviewJob(
            tenant_id=actor.tenant_id,
            file_id=file_id,
            version_id=version_id,
            requested_by=actor.id,
            request_id=payload.request_id,
            page=payload.page,
            generation=generation,
            storage_bucket=version.storage_bucket,
            namespace=storage_namespace(),
            next_attempt_at=now,
            expires_at=now + timedelta(seconds=TTL),
            cleanup_after=now
            + timedelta(
                seconds=TTL + settings.JOB_LEASE_SECONDS + settings.UPLOAD_CLEANUP_SETTLE_SECONDS
            ),
        )
        self.db.add(job)
        await self.db.commit()
        return PreviewJobRead(id=job.id, state=job.state, expires_at=job.expires_at)

    async def owned(self, actor, file_id, job_id):
        row = await self.db.scalar(
            select(PreviewJob)
            .where(
                PreviewJob.id == job_id,
                PreviewJob.file_id == file_id,
                PreviewJob.tenant_id == actor.tenant_id,
                PreviewJob.requested_by == actor.id,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise HTTPException(404, "Preview job not found")
        return snapshot(row)

    async def cancel(self, actor, file_id, job_id, ip=""):
        await AccountService(self.db).limit(
            "preview-job-cancel", ip, str(actor.id), max_identity=100, max_ip=500
        )
        job = await self.owned(actor, file_id, job_id)
        await self.db.execute(
            update(PreviewJob)
            .execution_options(synchronize_session=False)
            .where(PreviewJob.id == job.id)
            .values(
                state="cancelled",
                lease_id=None,
                lease_until=None,
            )
        )
        await self.db.commit()
        return PreviewJobRead(id=job.id, state="cancelled", expires_at=job.expires_at)

    async def get(self, actor, file_id, job_id, ip=""):
        actor = SimpleNamespace(id=actor.id, tenant_id=actor.tenant_id)
        await AccountService(self.db).limit(
            "preview-job-poll", ip, str(actor.id), max_identity=1500, max_ip=7500
        )
        job = await self.owned(actor, file_id, job_id)
        if utc(job.expires_at) <= datetime.now(UTC):
            return await self.cancel(actor, file_id, job_id)
        try:
            _, file, version = await self.authority(job)
        except HTTPException as error:
            if error.status_code in (403, 404, 409, 410):
                await self.cancel(actor, file_id, job_id)
            raise
        result = None
        if job.state == "ready":
            content = dict(job.metadata_json or {})
            if job.digest:
                try:
                    data = await self.storage.read_small(self.ref(job), 1024 * 1024)
                except StorageError:
                    raise HTTPException(503, "Preview result unavailable; retry later") from None
                if hashlib.sha256(data).hexdigest() != job.digest:
                    raise HTTPException(409, "Preview result changed")
                if content.get("kind") == "text":
                    content["text"] = data.decode("utf-8", errors="strict")
                else:
                    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise HTTPException(409, "Invalid preview result")
                    content["image_base64"] = base64.b64encode(data).decode()
            # Never publish a cached result on the authority checked before provider I/O.
            await self.db.rollback()
            latest = await self.owned(actor, file_id, job_id)
            try:
                _, file, version = await self.authority(latest)
            except HTTPException as error:
                if error.status_code in (403, 404, 409, 410):
                    await self.cancel(actor, file_id, job_id)
                raise
            if latest.state != "ready" or utc(latest.expires_at) <= datetime.now(UTC):
                raise HTTPException(409, "Preview expired or cancelled")
            result = PreviewRead(
                **content,
                file_id=file_id,
                version_id=version.id,
                version_number=version.number,
                name=file.name,
                generation=file.version_generation,
            )
        return PreviewJobRead(id=job.id, state=job.state, expires_at=job.expires_at, preview=result)

    @staticmethod
    def ref(job):
        return ObjectRef(job.tenant_id, job.file_id, job.artifact_id)

    async def claim(self, now=None):
        now = now or datetime.now(UTC)
        await self.db.execute(
            update(PreviewJob)
            .execution_options(synchronize_session=False)
            .where(
                PreviewJob.state == "running",
                PreviewJob.attempts >= 3,
                PreviewJob.lease_until <= now,
            )
            .values(state="failed", lease_id=None, lease_until=None)
        )
        eligible = (
            PreviewJob.expires_at > now,
            PreviewJob.attempts < 3,
            PreviewJob.next_attempt_at <= now,
            or_(
                PreviewJob.state == "queued",
                (PreviewJob.state == "running") & (PreviewJob.lease_until <= now),
            ),
        )
        job_id = await self.db.scalar(
            select(PreviewJob.id)
            .where(*eligible)
            .order_by(PreviewJob.next_attempt_at, PreviewJob.id)
            .limit(1)
        )
        if job_id is None:
            await self.db.commit()
            return None
        token = uuid4()
        result = await self.db.execute(
            update(PreviewJob)
            .execution_options(synchronize_session=False)
            .where(PreviewJob.id == job_id, *eligible)
            .values(
                state="running",
                attempts=PreviewJob.attempts + 1,
                lease_id=token,
                lease_until=now + timedelta(seconds=settings.JOB_LEASE_SECONDS),
            )
        )
        await self.db.commit()
        if result.rowcount != 1:
            return None
        return snapshot(await self.db.get(PreviewJob, job_id, populate_existing=True))

    async def process_next(self, job=None):
        job = job or await self.claim()
        if job is None:
            return "idle"
        try:
            current = await self.db.get(PreviewJob, job.id, populate_existing=True)
            if current is None or current.state != "running" or current.lease_id != job.lease_id:
                await self.db.rollback()
                return "superseded"
            actor, _, _ = await self.authority(job)
            preview = await PreviewService(self.db, self.storage, self.renderer).create(
                actor,
                job.file_id,
                PreviewRequest(version_id=job.version_id, page=job.page),
                "preview-worker",
            )
            data = (
                preview.text.encode("utf-8")
                if preview.kind == "text"
                else base64.b64decode(preview.image_base64, validate=True)
                if preview.image_base64
                else None
            )
            metadata = preview.model_dump(
                include={
                    "kind",
                    "detected_type",
                    "reason",
                    "width",
                    "height",
                    "page",
                    "pages",
                    "truncated",
                }
            )
            if data is not None and len(data) > 1024 * 1024:
                raise ValueError("Derivative limit")
            await self.db.rollback()
            await self.lock_tenant(job.tenant_id)
            current = await self.db.get(PreviewJob, job.id, populate_existing=True)
            now = datetime.now(UTC)
            if (
                current.lease_id != job.lease_id
                or current.state != "running"
                or utc(current.expires_at) <= now
                or utc(current.lease_until) <= now
            ):
                await self.db.rollback()
                return "superseded"
            await self.authority(job)
            digest = hashlib.sha256(data).hexdigest() if data is not None else None
            if data is not None:
                try:
                    await self.storage.put_small(self.ref(job), data)
                except ObjectConflictError:
                    prior = await self.storage.read_small(self.ref(job), 1024 * 1024)
                    if hashlib.sha256(prior).hexdigest() != digest:
                        raise StorageError("Conflicting preview derivative") from None
            result = await self.db.execute(
                update(PreviewJob)
                .execution_options(synchronize_session=False)
                .where(
                    PreviewJob.id == job.id,
                    PreviewJob.lease_id == job.lease_id,
                    PreviewJob.state == "running",
                    PreviewJob.expires_at > datetime.now(UTC),
                    PreviewJob.lease_until > datetime.now(UTC),
                )
                .values(
                    state="ready",
                    metadata_json=metadata,
                    digest=digest,
                    lease_id=None,
                    lease_until=None,
                )
            )
            await self.db.commit()
            return "ready" if result.rowcount else "superseded"
        except Exception as error:
            await self.db.rollback()
            cancelled = isinstance(error, HTTPException) and error.status_code in (
                403,
                404,
                409,
                410,
            )
            state = "cancelled" if cancelled else "failed" if job.attempts >= 3 else "queued"
            await self.db.execute(
                update(PreviewJob)
                .execution_options(synchronize_session=False)
                .where(
                    PreviewJob.id == job.id,
                    PreviewJob.lease_id == job.lease_id,
                )
                .values(
                    state=state,
                    lease_id=None,
                    lease_until=None,
                    next_attempt_at=datetime.now(UTC) + timedelta(seconds=2**job.attempts),
                )
            )
            await self.db.commit()
            return state

    async def cleanup_one(self, now=None, job_id=None):
        now = now or datetime.now(UTC)
        row = await self.db.scalar(
            select(PreviewJob)
            .where(
                PreviewJob.cleanup_after <= now,
                PreviewJob.namespace == storage_namespace(),
                *([PreviewJob.id == job_id] if job_id else []),
            )
            .order_by(PreviewJob.checked_at.asc().nullsfirst(), PreviewJob.id)
            .limit(1)
        )
        if row is None:
            await self.db.rollback()
            return "idle"
        job = snapshot(row)
        row.state, row.lease_id, row.lease_until, row.checked_at = "cancelled", None, None, now
        row.cleanup_failed = True
        await self.db.commit()
        try:
            versioning = await self.storage.call(self.storage.client.get_bucket_versioning)
            if versioning.get("Status") in ("Enabled", "Suspended"):
                raise StorageError("Preview cleanup requires unversioned storage")
            await self.storage.delete(self.ref(job))
            try:
                await self.storage.inspect_upload(self.ref(job))
            except ObjectNotFoundError:
                await self.db.execute(
                    update(PreviewJob)
                    .execution_options(synchronize_session=False)
                    .where(PreviewJob.id == job.id)
                    .values(cleanup_failed=False)
                )
                await self.db.commit()
                return "cleaned_reference_retained"
            return "deferred"
        except StorageError:
            return "deferred"
