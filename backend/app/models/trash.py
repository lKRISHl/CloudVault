from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TrashEntry(Base):
    __tablename__ = "trash_entries"
    __table_args__ = (
        CheckConstraint("kind IN ('files', 'folders')", name="ck_trash_kind"),
        Index("ix_trash_tenant", "tenant_id", "trashed_at", "id"),
        Index("ix_trash_maintenance", "checked_at", "retain_until"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    root_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(16))
    trashed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    trashed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    retain_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    purge_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
