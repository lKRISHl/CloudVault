from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ResourceOwner(Base):
    """Management authority; immutable creator/upload provenance stays on the resource."""

    __tablename__ = "resource_owners"
    __table_args__ = (
        CheckConstraint("(file_id IS NULL) <> (folder_id IS NULL)", name="ck_owner_resource"),
        UniqueConstraint("file_id", name="uq_owner_file"),
        UniqueConstraint("folder_id", name="uq_owner_folder"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    file_id: Mapped[UUID | None] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    folder_id: Mapped[UUID | None] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
