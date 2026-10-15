from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ResourceGrant(Base):
    __tablename__ = "resource_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            ondelete="CASCADE",
            name="fk_grant_membership",
        ),
        CheckConstraint("role IN ('viewer', 'editor')", name="ck_grant_role"),
        CheckConstraint("(file_id IS NULL) <> (folder_id IS NULL)", name="ck_grant_resource"),
        Index(
            "uq_grant_file",
            "file_id",
            "user_id",
            unique=True,
            postgresql_where=text("file_id IS NOT NULL"),
            sqlite_where=text("file_id IS NOT NULL"),
        ),
        Index(
            "uq_grant_folder",
            "folder_id",
            "user_id",
            unique=True,
            postgresql_where=text("folder_id IS NOT NULL"),
            sqlite_where=text("folder_id IS NOT NULL"),
        ),
        Index("ix_grant_actor", "tenant_id", "user_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    file_id: Mapped[UUID | None] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    folder_id: Mapped[UUID | None] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
