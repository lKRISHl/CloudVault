"""Quota admission under the existing tenant lock; retained references are authoritative.

No cached counter can drift or release space merely because a record is hidden/expired.
Provider inventory can increase an allocation; unknown sizes fail closed for new work.
"""

from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import case, exists, func, literal, select, union_all

from app.core.config import settings
from app.models import (
    File,
    FileVersion,
    PreviewJob,
    StorageObservation,
    StorageQuota,
    Tenant,
    UploadIntent,
)
from app.models.user import UserRole
from app.schemas.quotas import StorageUsage
from app.services.background_jobs import storage_namespace
from app.services.folders import FolderService


class QuotaService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def sources(tenant_id):
        # File mirrors its current snapshot; grouping exact identities counts it once.
        reclaimed_snapshot = exists().where(
            FileVersion.tenant_id == tenant_id,
            FileVersion.file_id == File.id,
            FileVersion.object_id == File.object_id,
            FileVersion.storage_bucket == File.storage_bucket,
            (FileVersion.cleaned_at.is_not(None) | FileVersion.purged_at.is_not(None)),
        )
        source = select(
            File.storage_bucket.label("bucket"),
            File.id.label("file_id"),
            File.object_id,
            File.declared_size_bytes.label("amount"),
            case((File.status == "uploaded", 0), else_=2).label("kind"),
            literal(0).label("unknown"),
        ).where(
            File.tenant_id == tenant_id,
            File.object_id.is_not(None),
            File.upload_cleanup_at.is_(None),
            File.object_purged_at.is_(None),
            ~reclaimed_snapshot,
        )
        versions = select(
            FileVersion.storage_bucket,
            FileVersion.file_id,
            FileVersion.object_id,
            FileVersion.declared_size_bytes,
            case((FileVersion.status == "uploaded", 0), else_=2),
            literal(0),
        ).where(
            FileVersion.tenant_id == tenant_id,
            FileVersion.cleaned_at.is_(None),
            FileVersion.purged_at.is_(None),
        )
        same_file = exists().where(
            File.tenant_id == tenant_id,
            File.id == UploadIntent.file_id,
            File.object_id == UploadIntent.object_id,
            File.storage_bucket == UploadIntent.storage_bucket,
        )
        same_version = exists().where(
            FileVersion.tenant_id == tenant_id,
            FileVersion.file_id == UploadIntent.file_id,
            FileVersion.object_id == UploadIntent.object_id,
            FileVersion.storage_bucket == UploadIntent.storage_bucket,
        )
        intents = select(
            UploadIntent.storage_bucket,
            UploadIntent.file_id,
            UploadIntent.object_id,
            func.coalesce(UploadIntent.reserved_bytes, 0),
            literal(2),
            case((UploadIntent.reserved_bytes.is_(None), 1), else_=0),
        ).where(
            UploadIntent.tenant_id == tenant_id,
            UploadIntent.cleaned_at.is_(None),
            ~same_file,
            ~same_version,
        )
        previews = select(
            PreviewJob.storage_bucket,
            PreviewJob.file_id,
            PreviewJob.artifact_id,
            PreviewJob.reserved_bytes,
            literal(1),
            literal(0),
        ).where(PreviewJob.tenant_id == tenant_id, PreviewJob.cleaned_at.is_(None))
        observations = select(
            StorageObservation.storage_bucket,
            StorageObservation.file_id,
            StorageObservation.object_id,
            func.coalesce(StorageObservation.size_bytes, 0),
            literal(3),
            case(
                (StorageObservation.size_bytes.is_(None), 1),
                (StorageObservation.namespace != storage_namespace(), 1),
                else_=0,
            ),
        ).where(StorageObservation.tenant_id == tenant_id)
        return union_all(source, versions, intents, previews, observations).subquery()

    async def usage(self, tenant_id):
        if await self.db.scalar(select(Tenant.id).where(Tenant.id == tenant_id)) is None:
            raise HTTPException(404, "Workspace not found")
        tenant = await self.db.get(StorageQuota, tenant_id, populate_existing=True)
        tenant = tenant or SimpleNamespace(
            storage_plan="free", storage_limit_bytes=None, quota_inventory=None
        )
        limit = tenant.storage_limit_bytes
        if limit is None:
            limit = (
                settings.STORAGE_TEAM_LIMIT_BYTES
                if tenant.storage_plan == "team"
                else settings.STORAGE_FREE_LIMIT_BYTES
            )
        source = self.sources(tenant_id)
        refs = (
            select(
                func.max(source.c.amount).label("amount"),
                func.min(source.c.kind).label("kind"),
                func.max(source.c.unknown).label("unknown"),
            )
            .group_by(source.c.bucket, source.c.file_id, source.c.object_id)
            .subquery()
        )
        totals = (
            await self.db.execute(
                select(
                    *[
                        func.coalesce(
                            func.sum(case((refs.c.kind == kind, refs.c.amount), else_=0)), 0
                        )
                        for kind in range(4)
                    ],
                    func.coalesce(func.sum(refs.c.unknown), 0),
                )
            )
        ).one()
        retained, derivatives, reserved, orphans, unresolved = map(int, totals)
        allocated = retained + derivatives + reserved + orphans
        return StorageUsage(
            plan=tenant.storage_plan,
            limit_bytes=limit,
            retained_bytes=retained,
            derivative_bytes=derivatives,
            reserved_bytes=reserved,
            orphan_bytes=orphans,
            allocated_bytes=allocated,
            available_bytes=max(0, limit - allocated),
            unresolved_references=unresolved,
            over_quota=allocated > limit,
            reconciliation_required=bool(
                unresolved
                or (tenant.quota_inventory or {}).get("failed")
                or tenant.quota_inventory
                and tenant.quota_inventory.get("namespace") not in (None, storage_namespace())
            ),
        )

    async def admit(self, tenant_id, amount):
        """Caller holds the tenant write lock; flush preceding allocations before summing."""
        if type(amount) is not int or amount < 0:
            raise ValueError("Invalid quota reservation")
        await self.db.flush()
        usage = await self.usage(tenant_id)
        if usage.reconciliation_required:
            raise HTTPException(409, "Storage accounting needs operator reconciliation")
        if usage.over_quota or amount > usage.available_bytes:
            raise HTTPException(403, "Workspace storage quota exceeded; free retained storage")

    async def read(self, actor):
        role = await FolderService(self.db).authorize(actor)
        if role not in (UserRole.OWNER, UserRole.ADMIN):
            raise HTTPException(403, "Workspace manager access required")
        return await self.usage(actor.tenant_id)
