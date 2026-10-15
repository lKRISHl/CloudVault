from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select, text

from app.core.config import settings
from app.models import File, Tenant, TrashEntry
from app.services.trash import file_scope, queue_purge
from app.services.uploads import utc
from app.storage.base import ObjectNotFoundError, ObjectRef, StorageError


class TrashCleanupService:
    """Irreversible provider cleanup of durably queued, retained trash references."""

    def __init__(self, db, storage):
        self.db, self.storage = db, storage

    async def sweep(self, entry_id, tenant_id, now=None):
        now = now or datetime.now(UTC)
        if self.db.bind.dialect.name == "sqlite":
            await self.db.execute(text("BEGIN IMMEDIATE"))
        await self.db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
        entry = await self.db.scalar(
            select(TrashEntry)
            .where(
                TrashEntry.id == entry_id,
                TrashEntry.tenant_id == tenant_id,
            )
            .execution_options(populate_existing=True)
        )
        if (
            entry is None
            or entry.restored_at
            or (entry.purge_requested_at is None and utc(entry.retain_until) > now)
        ):
            await self.db.rollback()
            return False
        # Commit the irreversible state before any provider deletion; a crash cannot allow restore.
        await queue_purge(self.db, entry, now)
        await self.db.commit()
        if self.db.bind.dialect.name == "sqlite":
            await self.db.execute(text("BEGIN IMMEDIATE"))
        await self.db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
        await self.db.refresh(entry)
        entry.checked_at = now
        if utc(entry.not_before) > now:
            await self.db.commit()
            return False
        try:
            versioning = await self.storage.call(self.storage.client.get_bucket_versioning)
            if versioning.get("Status") in ("Enabled", "Suspended"):
                raise StorageError("Trash cleanup requires an unversioned bucket")
            files = list(
                await self.db.scalars(
                    select(File)
                    .where(
                        File.tenant_id == tenant_id,
                        file_scope(entry),
                        File.trash_id.is_not(None),
                        File.status == "uploaded",
                        File.trash_id.in_(
                            select(TrashEntry.id).where(TrashEntry.not_before <= now)
                        ),
                    )
                    .order_by(File.purge_checked_at.asc().nullsfirst(), File.id)
                    .limit(10)
                )
            )
            for file in files:
                file.purge_checked_at = now
                if (
                    file.storage_bucket != settings.S3_BUCKET_NAME
                    or not file.object_id
                    or not file.upload_expires_at
                    or utc(file.upload_expires_at)
                    + timedelta(
                        seconds=settings.UPLOAD_COMPLETION_GRACE_SECONDS
                        + settings.UPLOAD_CLEANUP_SETTLE_SECONDS
                    )
                    > now
                ):
                    continue
                ref = ObjectRef(tenant_id, file.id, file.object_id)
                try:
                    for upload_id in await self.storage.pending_for_object(ref):
                        await self.storage.abort_multipart(ref, upload_id)
                    if await self.storage.pending_for_object(ref):
                        raise StorageError("Multipart uploads still exist")
                    await self.storage.delete(ref)
                    try:
                        await self.storage.inspect_upload(ref)
                    except ObjectNotFoundError:
                        pass
                    else:
                        raise StorageError("Object remains after deletion")
                    file.object_purged_at = file.object_purged_at or now
                except StorageError:
                    # Retain exact reference and rotate failed attempts; never report success early.
                    continue
            await self.db.flush()
            outstanding = await self.db.scalar(
                select(
                    exists().where(
                        File.tenant_id == tenant_id,
                        file_scope(entry),
                        File.trash_id.is_not(None),
                        File.status == "uploaded",
                        File.object_purged_at.is_(None),
                    )
                )
            )
            if not outstanding:
                entry.purged_at = entry.purged_at or now
            result = not outstanding
        except StorageError:
            result = False
        await self.db.commit()
        return result
