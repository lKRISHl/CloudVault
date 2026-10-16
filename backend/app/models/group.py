from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Group(Base):
    __tablename__ = "workspace_groups"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_group_tenant"),
        UniqueConstraint("tenant_id", "name_key", name="uq_group_name"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    name_key: Mapped[str] = mapped_column(String(768))


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["group_id", "tenant_id"],
            ["workspace_groups.id", "workspace_groups.tenant_id"],
            ondelete="CASCADE",
            name="fk_group_member_group",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            ondelete="CASCADE",
            name="fk_group_member_membership",
        ),
        Index("ix_group_member_actor", "tenant_id", "user_id"),
    )
    group_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)


class GroupGrant(Base):
    __tablename__ = "group_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["group_id", "tenant_id"],
            ["workspace_groups.id", "workspace_groups.tenant_id"],
            ondelete="CASCADE",
            name="fk_group_grant_group",
        ),
        CheckConstraint("role IN ('viewer','editor')", name="ck_group_grant_role"),
        CheckConstraint("(file_id IS NULL) <> (folder_id IS NULL)", name="ck_group_grant_resource"),
        UniqueConstraint("file_id", "group_id", name="uq_group_grant_file"),
        UniqueConstraint("folder_id", "group_id", name="uq_group_grant_folder"),
        Index("ix_group_grant_actor", "tenant_id", "group_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    group_id: Mapped[UUID] = mapped_column(nullable=False)
    file_id: Mapped[UUID | None] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    folder_id: Mapped[UUID | None] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
