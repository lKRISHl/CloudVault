"""Version-bound quarantine, leases and release. PostgreSQL never receives file bytes."""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, text, update

from app.core.config import settings
from app.models import File, FileVersion, Tenant
from app.scanning.clamd import ClamdScanner
from app.services.background_jobs import storage_namespace
from app.services.uploads import utc
from app.storage.base import ObjectRef, StorageError


def policy():
    return hashlib.sha256(
        f"clamav-v1|{settings.SCAN_MAX_BYTES}|{storage_namespace()}".encode()
    ).hexdigest()


def fingerprint(version):
    values = {
        key: str(getattr(version, key))
        for key in (
            "id",
            "tenant_id",
            "file_id",
            "object_id",
            "storage_bucket",
            "size_bytes",
            "declared_size_bytes",
            "checksum_sha256",
            "expected_checksum_sha256",
            "storage_etag",
            "content_type",
            "checksum_kind",
            "multipart_part_size",
            "multipart_count",
        )
    }
    values["namespace"] = storage_namespace()
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


async def require_released(db, file, version=None):
    # Always reload the exact object, including historical downloads and existing derivatives.
    row = await db.scalar(
        select(FileVersion)
        .where(
            FileVersion.tenant_id == file.tenant_id,
            FileVersion.file_id == file.id,
            FileVersion.object_id == (version.object_id if version else file.object_id),
        )
        .execution_options(populate_existing=True)
    )
    if (
        row is None
        or row.status != "uploaded"
        or row.scan_status != "clean"
        or row.scan_policy != policy()
        or row.scan_fingerprint != fingerprint(row)
        or row.scanned_at is None
        or not row.scan_engine
        or row.cleaned_at
        or row.purged_at
        or row.prune_requested_at
    ):
        raise HTTPException(
            423, "Content quarantined: a successful current-policy scan is required"
        )
    return row


class ScanService:
    def __init__(self, db, storage=None, scanner=None):
        self.db, self.storage = db, storage
        self.scanner = scanner or ClamdScanner()

    async def claim(self):
        now = datetime.now(UTC)
        if self.db.bind.dialect.name == "sqlite":
            await self.db.execute(text("BEGIN IMMEDIATE"))
        row = await self.db.scalar(
            select(FileVersion)
            .where(
                FileVersion.status == "uploaded",
                FileVersion.cleaned_at.is_(None),
                FileVersion.purged_at.is_(None),
                FileVersion.prune_requested_at.is_(None),
                or_(
                    FileVersion.scan_next_attempt_at.is_(None),
                    FileVersion.scan_next_attempt_at <= now,
                ),
                or_(
                    FileVersion.scan_status == "pending",
                    (FileVersion.scan_status == "error") & (FileVersion.scan_attempts < 3),
                    (FileVersion.scan_status == "scanning") & (FileVersion.scan_lease_until <= now),
                    (FileVersion.scan_status == "clean") & (FileVersion.scan_policy != policy()),
                ),
            )
            .order_by(
                FileVersion.scan_attempts,
                FileVersion.scan_next_attempt_at.asc().nullsfirst(),
                FileVersion.id,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            await self.db.rollback()
            return None
        if row.scan_status == "clean":
            row.scan_attempts = 0
        if row.scan_attempts >= 3:
            row.scan_status, row.scan_lease_id, row.scan_lease_until = "error", None, None
            await self.mirror(row)
            await self.db.commit()
            return None
        row.scan_status, row.scan_lease_id = "scanning", uuid4()
        row.scan_lease_until = now + timedelta(seconds=settings.JOB_LEASE_SECONDS)
        row.scan_attempts += 1
        await self.mirror(row)
        await self.db.commit()
        return SimpleNamespace(**{c.name: getattr(row, c.name) for c in row.__table__.columns})

    async def mirror(self, version):
        await self.db.execute(
            update(File)
            .where(
                File.id == version.file_id,
                File.tenant_id == version.tenant_id,
                File.object_id == version.object_id,
                File.current_version == version.number,
            )
            .values(scan_status=version.scan_status)
        )

    async def verified_chunks(self, version):
        if (
            version.size_bytes != version.declared_size_bytes
            or version.checksum_sha256 != version.expected_checksum_sha256
            or version.checksum_kind not in ("sha256", "sha256-composite")
            or (
                version.checksum_kind == "sha256-composite"
                and (
                    not version.multipart_part_size
                    or version.multipart_part_size < 1
                    or not version.multipart_count
                    or not 1 <= version.multipart_count <= 1024
                )
            )
        ):
            raise StorageError("Invalid verified scan source")
        ref = ObjectRef(version.tenant_id, version.file_id, version.object_id)
        info = await self.storage.inspect_upload(ref)
        expected = (
            f"{version.checksum_sha256}-{version.multipart_count}"
            if version.checksum_kind == "sha256-composite"
            else version.checksum_sha256
        )
        if (
            info.size_bytes != version.size_bytes
            or info.etag != version.storage_etag
            or info.checksum_sha256 != expected
            or info.content_type != "application/octet-stream"
            or version.storage_bucket != settings.S3_BUCKET_NAME
        ):
            raise StorageError("Scan source no longer matches verification")
        digest, part_digest, parts = hashlib.sha256(), hashlib.sha256(), bytearray()
        count, used, total = 0, 0, 0
        source = self.storage.stream_for_scanning(ref, version.storage_etag, version.size_bytes)
        try:
            async for chunk in source:
                if not isinstance(chunk, bytes) or not 0 < len(chunk) <= 65536:
                    raise StorageError("Invalid scan chunk")
                total += len(chunk)
                if total > version.size_bytes or total > settings.SCAN_MAX_BYTES:
                    raise StorageError("Scan input exceeds verification")
                digest.update(chunk)
                if version.checksum_kind == "sha256-composite":
                    if not version.multipart_part_size or not version.multipart_count:
                        raise StorageError("Invalid composite declaration")
                    offset = 0
                    while offset < len(chunk):
                        amount = min(version.multipart_part_size - used, len(chunk) - offset)
                        part_digest.update(chunk[offset : offset + amount])
                        used += amount
                        offset += amount
                        if used == version.multipart_part_size:
                            parts.extend(part_digest.digest())
                            count, used, part_digest = count + 1, 0, hashlib.sha256()
                            if count > 1024:
                                raise StorageError("Composite scan bound exceeded")
                yield chunk
            if version.checksum_kind == "sha256-composite":
                if used:
                    parts.extend(part_digest.digest())
                    count += 1
                if count != version.multipart_count:
                    raise StorageError("Composite part count changed")
                digest = hashlib.sha256(parts)
            if (
                total != version.size_bytes
                or base64.b64encode(digest.digest()).decode() != version.checksum_sha256
            ):
                raise StorageError("Scan source checksum changed")
        finally:
            await source.aclose()

    async def process(self, job):
        state, engine = "error", None
        proof, scan_policy = fingerprint(job), policy()
        if job.size_bytes is None or job.size_bytes > settings.SCAN_MAX_BYTES:
            state = "oversized"
        else:
            fully_verified = False

            async def verified_stream():
                nonlocal fully_verified
                source = self.verified_chunks(job)
                try:
                    async for chunk in source:
                        yield chunk
                    fully_verified = True
                finally:
                    await source.aclose()

            chunks = verified_stream()
            try:
                state, engine = await self.scanner.scan(chunks)
                if (
                    not fully_verified
                    or state not in ("clean", "blocked")
                    or not engine
                    or len(engine) > 128
                ):
                    state, engine = "error", None
            except Exception:
                state, engine = "error", None
            finally:
                await chunks.aclose()
        await self.db.rollback()
        # Same tenant lock as version activation/trash; UUID+expiry fences stale publication.
        if self.db.bind.dialect.name == "sqlite":
            await self.db.execute(text("BEGIN IMMEDIATE"))
        await self.db.scalar(select(Tenant.id).where(Tenant.id == job.tenant_id).with_for_update())
        row = await self.db.scalar(
            select(FileVersion)
            .where(FileVersion.id == job.id, FileVersion.tenant_id == job.tenant_id)
            .execution_options(populate_existing=True)
        )
        if (
            row is None
            or row.scan_lease_id != job.scan_lease_id
            or row.scan_status != "scanning"
            or not row.scan_lease_until
            or utc(row.scan_lease_until) <= datetime.now(UTC)
        ):
            await self.db.rollback()
            return "superseded"
        if (
            fingerprint(row) != proof
            or scan_policy != policy()
            or row.status != "uploaded"
            or row.cleaned_at
            or row.purged_at
            or row.prune_requested_at
        ):
            state, engine = "error", None
        row.scan_status, row.scan_engine = state, engine
        row.scan_policy, row.scan_fingerprint = scan_policy, proof
        row.scan_lease_id, row.scan_lease_until = None, None
        row.scanned_at = datetime.now(UTC) if state in ("clean", "blocked") else None
        row.scan_next_attempt_at = datetime.now(UTC) + timedelta(seconds=2**row.scan_attempts)
        await self.mirror(row)
        await self.db.commit()
        return state

    async def retry(self, actor, file_id, version_id, ip):
        from app.services.accounts import AccountService
        from app.services.versions import VersionService

        await AccountService(self.db).limit("scan-retry", ip, str(actor.id))
        service = VersionService(self.db)
        file, _ = await service.access(actor, file_id, write=True)
        # Serialize against a worker claim too; the tenant lock alone does not cover claims.
        await self.db.scalar(
            select(FileVersion.id)
            .where(
                FileVersion.id == version_id,
                FileVersion.file_id == file.id,
                FileVersion.tenant_id == actor.tenant_id,
            )
            .with_for_update()
        )
        version = await service.find(actor, file, version_id)
        if version.status != "uploaded" or version.scan_status != "error":
            raise HTTPException(
                409, "Only a failed scan can be retried; blocked content needs replacement"
            )
        version.scan_status, version.scan_attempts = "pending", 0
        version.scan_next_attempt_at = version.scan_lease_id = version.scan_lease_until = None
        await self.mirror(version)
        await self.db.commit()
        return {"detail": "Scan queued; content remains quarantined"}
