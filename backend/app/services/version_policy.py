from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models import FileVersion, FileVersionChange
from app.services.uploads import utc


def queue_prune(version, now):
    if version.prune_requested_at is None:
        version.prune_requested_at = now
        # Preserve all GET grants issued before this irreversible request (configured max 900s).
        version.prune_not_before = max(
            utc(version.upload_expires_at)
            + timedelta(seconds=settings.UPLOAD_COMPLETION_GRACE_SECONDS),
            now + timedelta(seconds=900),
        ) + timedelta(seconds=settings.UPLOAD_CLEANUP_SETTLE_SECONDS)


async def apply_policy(db, file, now=None):
    now = now or datetime.now(UTC)
    if file.version_keep_last is None or file.trash_id or file.status != "uploaded":
        return 0
    file.version_policy_checked_at = now
    retained = (
        select(FileVersion.id)
        .where(
            FileVersion.tenant_id == file.tenant_id,
            FileVersion.file_id == file.id,
            FileVersion.status == "uploaded",
            FileVersion.prune_requested_at.is_(None),
            FileVersion.purged_at.is_(None),
        )
        .order_by(FileVersion.completed_at.desc(), FileVersion.number.desc())
        .limit(file.version_keep_last)
    )
    candidates = list(
        await db.scalars(
            select(FileVersion)
            .where(
                FileVersion.tenant_id == file.tenant_id,
                FileVersion.file_id == file.id,
                FileVersion.status == "uploaded",
                FileVersion.prune_requested_at.is_(None),
                FileVersion.purged_at.is_(None),
                FileVersion.number != file.current_version,
                FileVersion.id.not_in(retained),
            )
            .order_by(FileVersion.number)
            .limit(100)
        )
    )
    for version in candidates:
        queue_prune(version, now)
    return len(candidates)


class VersionPolicyService:
    def __init__(self, db):
        self.db = db

    async def managed(self, actor, file_id):
        from app.services.permissions import PermissionService
        from app.services.versions import VersionService

        file, role = await VersionService(self.db).access(actor, file_id, True)
        if not PermissionService.manages(actor, role, file):
            raise HTTPException(403, "Creator or workspace manager required")
        return file, role

    async def prune(self, actor, file_id, version_id, ip):
        from app.services.accounts import AccountService

        await AccountService(self.db).limit("version-prune", ip, str(actor.id))
        file, _ = await self.managed(actor, file_id)
        version = await self.db.scalar(
            select(FileVersion).where(
                FileVersion.id == version_id,
                FileVersion.file_id == file.id,
                FileVersion.tenant_id == actor.tenant_id,
            )
        )
        if version is None or version.purged_at:
            raise HTTPException(404, "Version not found")
        if version.status != "uploaded" or version.number == file.current_version:
            raise HTTPException(409, "Only completed non-current history can be pruned")
        queue_prune(version, datetime.now(UTC))
        self.db.add(
            FileVersionChange(
                tenant_id=file.tenant_id,
                file_id=file.id,
                actor_id=actor.id,
                number=version.number,
                generation=file.version_generation,
                reason="prune",
            )
        )
        await self.db.commit()
        return {"detail": "Version deletion queued; bytes remain counted until confirmed cleanup"}

    async def configure(self, actor, file_id, keep_last, ip):
        from app.services.accounts import AccountService
        from app.services.files import FileService

        await AccountService(self.db).limit("version-policy", ip, str(actor.id))
        file, role = await self.managed(actor, file_id)
        file.version_keep_last = keep_last
        self.db.add(
            FileVersionChange(
                tenant_id=file.tenant_id,
                file_id=file.id,
                actor_id=actor.id,
                number=file.current_version,
                generation=file.version_generation,
                reason="policy",
            )
        )
        await apply_policy(self.db, file)
        await self.db.commit()
        await self.db.refresh(file)
        return FileService.read(actor, role, file)
