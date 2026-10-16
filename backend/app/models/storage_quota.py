"""Workspace storage policy, separate from authentication identity."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StorageQuota(Base):
    __tablename__ = "storage_quotas"
    __table_args__ = (
        CheckConstraint("storage_plan IN ('free','team')", name="ck_storage_quota_plan"),
        CheckConstraint(
            "storage_limit_bytes IS NULL OR storage_limit_bytes >= 0", name="ck_storage_quota_limit"
        ),
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    storage_plan: Mapped[str] = mapped_column(String(16), default="free", server_default="free")
    storage_limit_bytes: Mapped[int | None] = mapped_column(BigInteger)
    quota_inventory: Mapped[dict | None] = mapped_column(JSON)
    quota_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    @property
    def id(self):
        return self.tenant_id
