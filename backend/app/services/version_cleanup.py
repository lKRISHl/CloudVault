from datetime import UTC, datetime

from sqlalchemy import select, text

from app.core.config import settings
from app.models import FileVersion, Tenant
from app.services.upload_cleanup import UploadCleanupService
from app.services.uploads import utc
from app.storage.base import ObjectNotFoundError, ObjectRef, StorageError


async def remove_object(storage, tenant_id, file_id, version):
    ref = ObjectRef(tenant_id, file_id, version.object_id)
    for upload_id in await storage.pending_for_object(ref):
        await storage.abort_multipart(ref, upload_id)
    if await storage.pending_for_object(ref):
        raise StorageError("Multipart uploads still exist")
    await storage.delete(ref)
    try:
        await storage.inspect_upload(ref)
    except ObjectNotFoundError:
        return
    raise StorageError("Object remains after deletion")


class VersionCleanupService:
    def __init__(self, db, storage):
        self.db, self.storage = db, storage

    async def sweep(self, version_id, tenant_id, now=None):
        now = now or datetime.now(UTC)
        if self.db.bind.dialect.name == "sqlite":
            await self.db.execute(text("BEGIN IMMEDIATE"))
        await self.db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
        version = await self.db.scalar(
            select(FileVersion)
            .where(
                FileVersion.id == version_id,
                FileVersion.tenant_id == tenant_id,
            )
            .execution_options(populate_existing=True)
        )
        if (
            version is None
            or version.status != "pending"
            or utc(version.upload_expires_at) > UploadCleanupService.cutoff(now)
            or version.storage_bucket != settings.S3_BUCKET_NAME
        ):
            await self.db.rollback()
            return False
        version.checked_at = now
        try:
            state = await self.storage.call(self.storage.client.get_bucket_versioning)
            if state.get("Status") in ("Enabled", "Suspended"):
                raise StorageError("Version cleanup requires an unversioned bucket")
            await remove_object(self.storage, tenant_id, version.file_id, version)
            version.cleaned_at = version.cleaned_at or now
            result = True
        except StorageError:
            result = False
        await self.db.commit()
        return result
