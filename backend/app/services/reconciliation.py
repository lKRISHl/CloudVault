"""Privileged, explicit legacy retirement. Retain every exact reference for late-write retries."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, or_, select, text, update

from app.core.config import settings
from app.models import File, FileVersion, Tenant, UploadIntent, UserRole
from app.services.folders import FolderService
from app.services.upload_cleanup import UploadCleanupService
from app.services.uploads import utc
from app.services.version_cleanup import remove_object
from app.services.versions import VersionService
from app.storage.base import ObjectNotFoundError, ObjectRef, StorageError


class ReconciliationService:
    def __init__(self, db, storage=None):
        self.db, self.storage = db, storage

    async def records(self, tenant_id, file_id, *, lock=False, diagnostic=False, offset=0):
        if lock:
            if self.db.bind.dialect.name == "sqlite":
                await self.db.execute(text("BEGIN IMMEDIATE"))
            await self.db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
        file = await self.db.scalar(
            select(File)
            .where(
                File.id == file_id,
                File.tenant_id == tenant_id,
            )
            .execution_options(populate_existing=True)
        )
        intent = await self.db.get(UploadIntent, file_id, populate_existing=True)
        if file is None and (intent is None or intent.tenant_id != tenant_id):
            raise ValueError("Legacy metadata not found in selected tenant")
        if file is None and await self.db.get(File, file_id) is not None:
            raise ValueError("Contradictory tenant references; individual review required")
        versions = list(
            await self.db.scalars(
                select(FileVersion)
                .where(
                    FileVersion.file_id == file_id,
                )
                .order_by(FileVersion.number)
                .offset(offset)
                .limit(26 if diagnostic else 1)
                .execution_options(populate_existing=True)
            )
        )
        foreign_version = await self.db.scalar(
            select(FileVersion.id)
            .where(
                FileVersion.file_id == file_id,
                FileVersion.tenant_id != tenant_id,
            )
            .limit(1)
        )
        if foreign_version or intent and intent.tenant_id != tenant_id:
            raise ValueError("Contradictory tenant references; individual review required")
        return file, intent, versions

    async def diagnose(self, tenant_id, file_id, *, offset=0):
        if type(offset) is not int or not 0 <= offset <= 100000:
            raise ValueError("Invalid diagnostic offset")
        file, intent, versions = await self.records(
            tenant_id, file_id, diagnostic=True, offset=offset
        )
        has_more = len(versions) > 25
        versions = versions[:25]
        refs = []
        for kind, record in [
            *([("intent", intent)] if intent else []),
            *(("version", item) for item in versions),
        ]:
            expires = record.expires_at if kind == "intent" else record.upload_expires_at
            refs.append(
                {
                    "kind": kind,
                    "version_id": str(record.id) if kind == "version" else None,
                    "multipart_upload_id": record.multipart_upload_id
                    if kind == "version"
                    else None,
                    "key": ObjectRef(tenant_id, file_id, record.object_id).key,
                    "bucket": record.storage_bucket,
                    "expires_at": utc(expires).isoformat(),
                    "status": "initialization" if kind == "intent" else record.status,
                }
            )
        if file and file.object_id:
            refs.append(
                {
                    "kind": "file",
                    "key": ObjectRef(tenant_id, file_id, file.object_id).key,
                    "bucket": file.storage_bucket,
                    "expires_at": utc(file.upload_expires_at).isoformat(),
                    "status": file.status,
                    "multipart_upload_id": file.multipart_upload_id,
                }
            )
        allowed = (file is None or file.status == "pending" and file.object_id is None) and all(
            item.status == "pending" for item in versions
        )
        return {
            "tenant_id": str(tenant_id),
            "file_id": str(file_id),
            "metadata_status": file.status if file else "unmaterialized",
            "folder_id": str(intent.folder_id) if intent and intent.folder_id else None,
            "scope_recorded": intent.scope_recorded if intent else None,
            "retirement_allowed": allowed if not has_more and offset == 0 else None,
            "version_offset": offset,
            "next_version_offset": offset + 25 if has_more else None,
            "references": refs,
            "meaning": "operator inventory; no provider absence proof",
        }

    async def adopt(self, tenant_id, file_id, version_id, operator_user, *, confirmed_file_id):
        if confirmed_file_id != file_id:
            raise ValueError("Exact file confirmation required")
        actor = SimpleNamespace(id=operator_user, tenant_id=tenant_id)
        folders = FolderService(self.db)
        role = await folders.authorize(actor, write=True)
        if role not in (UserRole.OWNER, UserRole.ADMIN):
            raise ValueError("Adoption requires an active verified workspace manager")
        file, intent, _ = await self.records(tenant_id, file_id)
        if (
            file is None
            or file.status != "pending"
            or file.object_id is not None
            or file.upload_cancelled_at
            or file.upload_cleanup_at
            or file.trash_id is not None
        ):
            raise ValueError("Only live legacy metadata can adopt a retained completed version")
        path = await folders.ancestors(actor, file.folder_id)
        if path:
            await folders.require_write(actor, role, path[-1])
        version = await self.db.scalar(
            select(FileVersion).where(
                FileVersion.file_id == file_id,
                FileVersion.tenant_id == tenant_id,
                FileVersion.id == version_id,
            )
        )
        if (
            version is None
            or version.status != "uploaded"
            or version.cleaned_at
            or version.purged_at
            or version.prune_requested_at
            or version.storage_bucket != settings.S3_BUCKET_NAME
        ):
            raise ValueError("Selected completed version is unavailable")
        ref = ObjectRef(tenant_id, file_id, version.object_id)
        versioning = await self.storage.call(self.storage.client.get_bucket_versioning)
        if versioning.get("Status") in ("Enabled", "Suspended"):
            raise StorageError("Reconciliation requires unversioned storage")
        info = await self.storage.inspect_upload(ref)
        checksum = (
            f"{version.checksum_sha256}-{version.multipart_count}"
            if version.checksum_kind == "sha256-composite"
            else version.checksum_sha256
        )
        if (
            info.size_bytes != version.size_bytes
            or info.checksum_sha256 != checksum
            or info.etag != version.storage_etag
            or info.content_type != "application/octet-stream"
        ):
            raise ValueError("Retained provider object differs from verified version")
        # Use the existing activation/change history/share invalidation policy; no invented bytes.
        file.status = "uploaded"
        # This is an operator adoption, not replay of an original initialization request.
        file.upload_request_id = uuid4()
        await VersionService(self.db, self.storage).activate(actor, file, version, "restore")
        if intent:
            intent.cancelled_at = intent.cancelled_at or datetime.now(UTC)
        await self.db.commit()
        return "adopted_verified_version_references_retained"

    async def retirement_deadline(self, tenant_id, file_id, file, intent):
        completed = await self.db.scalar(
            select(FileVersion.id)
            .where(
                FileVersion.file_id == file_id,
                FileVersion.status != "pending",
            )
            .limit(1)
        )
        if completed:
            raise ValueError("Retained completed content requires adoption; retirement refused")
        changed = await self.db.scalar(
            select(FileVersion.id)
            .where(
                FileVersion.file_id == file_id,
                FileVersion.storage_bucket != settings.S3_BUCKET_NAME,
            )
            .limit(1)
        )
        if changed or intent and intent.storage_bucket != settings.S3_BUCKET_NAME:
            raise ValueError("Storage configuration changed; references retained")
        latest = await self.db.scalar(
            select(func.max(FileVersion.upload_expires_at)).where(
                FileVersion.file_id == file_id,
                FileVersion.tenant_id == tenant_id,
            )
        )
        deadlines = [
            utc(value)
            for value in (
                latest,
                intent.expires_at if intent else None,
                file.upload_expires_at if file else None,
            )
            if value is not None
        ]
        return max(deadlines) if deadlines else None

    async def retire(self, tenant_id, file_id, *, confirmed_file_id, now=None):
        if confirmed_file_id != file_id:
            raise ValueError("Exact file confirmation required")
        now = now or datetime.now(UTC)
        file, intent, _ = await self.records(tenant_id, file_id, lock=True)
        if file is not None and (file.status != "pending" or file.object_id is not None):
            raise ValueError("Only contradictory legacy pending metadata can be retired")
        deadline = await self.retirement_deadline(tenant_id, file_id, file, intent)
        if file:
            file.upload_cancelled_at = file.upload_cancelled_at or now
        if intent:
            intent.cancelled_at = intent.cancelled_at or now
        await self.db.execute(
            update(FileVersion)
            .where(
                FileVersion.file_id == file_id,
                FileVersion.tenant_id == tenant_id,
                FileVersion.status == "pending",
                FileVersion.cancelled_at.is_(None),
            )
            .values(cancelled_at=now)
        )
        # Cancellation survives provider errors and invalidates retries before any I/O.
        await self.db.commit()
        if deadline and deadline > UploadCleanupService.cutoff(now):
            return "waiting_for_original_deadlines"
        # Re-read under the same lock used by uploads/trash before destructive provider work.
        file, intent, _ = await self.records(tenant_id, file_id, lock=True)
        if file is not None and (file.status != "pending" or file.object_id is not None):
            raise ValueError("Metadata changed; retirement refused")
        deadline = await self.retirement_deadline(tenant_id, file_id, file, intent)
        if deadline and deadline > UploadCleanupService.cutoff(now):
            await self.db.rollback()
            return "waiting_for_original_deadlines"
        versions = list(
            await self.db.scalars(
                select(FileVersion)
                .where(
                    FileVersion.file_id == file_id,
                    FileVersion.tenant_id == tenant_id,
                )
                .order_by(FileVersion.checked_at.asc().nullsfirst(), FileVersion.number)
                .limit(settings.STORAGE_STAGE_BATCH_SIZE)
            )
        )
        if self.storage is None:
            raise ValueError("Storage dependency required for absence proof")
        versioning = await self.storage.call(self.storage.client.get_bucket_versioning)
        if versioning.get("Status") in ("Enabled", "Suspended"):
            raise StorageError("Reconciliation requires unversioned storage")
        for version in versions:
            await remove_object(self.storage, tenant_id, file_id, version)
            version.cleaned_at = version.cleaned_at or now
            version.checked_at = now
        if intent:
            ref = ObjectRef(tenant_id, file_id, intent.object_id)
            for upload_id in await self.storage.pending_for_object(ref):
                await self.storage.abort_multipart(ref, upload_id)
            if await self.storage.pending_for_object(ref):
                raise StorageError("Initialization uploads remain")
            await self.storage.delete(ref)
            try:
                await self.storage.inspect_upload(ref)
            except ObjectNotFoundError:
                pass
            else:
                raise StorageError("Initialization object remains")
            intent.checked_at = now
        remaining = await self.db.scalar(
            select(FileVersion.id)
            .where(
                FileVersion.file_id == file_id,
                FileVersion.tenant_id == tenant_id,
                or_(FileVersion.cleaned_at.is_(None), FileVersion.cancelled_at.is_(None)),
            )
            .limit(1)
        )
        if file and not remaining:
            file.upload_cleanup_at = file.upload_cleanup_at or now
        await self.db.commit()
        return "cleanup_in_progress" if remaining else "retired_references_retained"
