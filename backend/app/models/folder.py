from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_folders_id_tenant"),
        ForeignKeyConstraint(
            ["parent_id", "tenant_id"],
            ["folders.id", "folders.tenant_id"],
            name="fk_folders_parent_tenant",
        ),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_folders_not_self_parent"),
        CheckConstraint("visibility IN ('workspace', 'private')", name="ck_folders_visibility"),
        UniqueConstraint("tenant_id", "parent_id", "name_key", name="uq_folders_sibling_name"),
        Index(
            "uq_folders_root_name",
            "tenant_id",
            "name_key",
            unique=True,
            postgresql_where=text("parent_id IS NULL"),
            sqlite_where=text("parent_id IS NULL"),
        ),
        Index("ix_folders_children", "tenant_id", "parent_id", "name", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_key: Mapped[str] = mapped_column(String(768), nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(16), default="workspace", server_default="workspace"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
