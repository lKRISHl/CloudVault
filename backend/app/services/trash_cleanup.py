from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, or_, select, text

from app.core.config import settings
from app.models import File, FileVersion, Tenant, TrashEntry
from app.services.trash import file_scope, queue_purge
from app.services.uploads import utc
from app.services.version_cleanup import remove_object
from app.storage.base import StorageError


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
                versions = list(
                    await self.db.scalars(
                        select(FileVersion)
                        .where(
                            FileVersion.tenant_id == tenant_id,
                            FileVersion.file_id == file.id,
                        )
                        .order_by(FileVersion.checked_at.asc().nullsfirst(), FileVersion.number)
                        .limit(10)
                    )
                )
                # Legacy rows without snapshots still retain their original exact reference.
                for version in versions or [file]:
                    if versions:
                        version.checked_at = now
                    if (
                        version.storage_bucket != settings.S3_BUCKET_NAME
                        or not version.object_id
                        or not version.upload_expires_at
                        or utc(version.upload_expires_at)
                        + timedelta(
                            seconds=settings.UPLOAD_COMPLETION_GRACE_SECONDS
                            + settings.UPLOAD_CLEANUP_SETTLE_SECONDS
                        )
                        > now
                        or (
                            versions
                            and version.prune_not_before is not None
                            and utc(version.prune_not_before) > now
                        )
                    ):
                        continue
                    try:
                        await remove_object(self.storage, tenant_id, file.id, version)
                        if versions:
                            if version.status == "pending":
                                version.cleaned_at = version.cleaned_at or now
                            else:
                                version.purged_at = version.purged_at or now
                        else:
                            file.object_purged_at = file.object_purged_at or now
                    except StorageError:
                        continue
                await self.db.flush()
                remaining = await self.db.scalar(
                    select(
                        exists().where(
                            FileVersion.tenant_id == tenant_id,
                            FileVersion.file_id == file.id,
                            or_(
                                and_(
                                    FileVersion.status == "uploaded",
                                    FileVersion.purged_at.is_(None),
                                ),
                                and_(
                                    FileVersion.status == "pending",
                                    FileVersion.cleaned_at.is_(None),
                                ),
                            ),
                        )
                    )
                )
                if versions and not remaining:
                    file.object_purged_at = file.object_purged_at or now
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
