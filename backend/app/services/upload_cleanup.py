"""Privileged maintenance of expired transfers; never delete completed files."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from app.core.config import settings
from app.models import File, Tenant
from app.services.uploads import utc
from app.storage.base import MultipartNotFoundError, ObjectNotFoundError, ObjectRef, StorageError


class UploadCleanupService:
    def __init__(self, db, storage):
        self.db, self.storage = db, storage

    @staticmethod
    def cutoff(now):
        return now - timedelta(
            seconds=settings.UPLOAD_COMPLETION_GRACE_SECONDS
            + settings.UPLOAD_CLEANUP_SETTLE_SECONDS
        )

    async def sweep(self, file_id, tenant_id, now=None):
        now = now or datetime.now(UTC)
        if self.db.bind.dialect.name == "sqlite":
            await self.db.execute(text("BEGIN IMMEDIATE"))
        await self.db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
        file = await self.db.scalar(
            select(File)
            .where(File.id == file_id, File.tenant_id == tenant_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            file is None
            or file.status != "pending"
            or not file.object_id
            or not file.upload_expires_at
            or file.storage_bucket != settings.S3_BUCKET_NAME
            or utc(file.upload_expires_at) > self.cutoff(now)
        ):
            await self.db.rollback()
            return False
        ref = ObjectRef(tenant_id, file.id, file.object_id)
        try:
            # Repeated maintenance catches writes that finish after an earlier abort/delete.
            if file.upload_method == "multipart":
                for upload_id in await self.storage.pending_for_object(ref):
                    await self.storage.abort_multipart(ref, upload_id)
                await self.storage.abort_multipart(ref, file.multipart_upload_id)
                try:
                    await self.storage.list_parts(ref, file.multipart_upload_id)
                except MultipartNotFoundError:
                    pass
                else:
                    raise StorageError("Provider still exposes an active multipart upload")
            await self.storage.delete(ref)
            try:
                await self.storage.inspect_upload(ref)
            except ObjectNotFoundError:
                pass
            else:
                raise StorageError("Provider still exposes an abandoned object")
            file.upload_cleanup_at = file.upload_cleanup_at or now
            if file.upload_method == "multipart":
                file.multipart_state = "aborted"
            result = True
        except StorageError:
            # Preserve name/references on failure; rotate attempts fairly across the queue.
            result = False
        file.upload_cleanup_checked_at = now
        await self.db.commit()
        return result
