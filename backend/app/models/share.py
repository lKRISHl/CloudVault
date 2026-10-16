from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ShareLink(Base):
    __tablename__ = "share_links"
    __table_args__ = (
        CheckConstraint("(file_id IS NULL) <> (folder_id IS NULL)", name="ck_share_resource"),
        UniqueConstraint("tenant_id", "created_by", "request_id", name="uq_share_request"),
        Index("ix_share_folder", "tenant_id", "folder_id", "created_at", "id"),
        CheckConstraint("download_grants >= 0", name="ck_share_grants"),
        CheckConstraint(
            "max_downloads IS NULL OR max_downloads BETWEEN 1 AND 10000", name="ck_share_max"
        ),
        Index("ix_share_file", "tenant_id", "file_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    file_id: Mapped[UUID | None] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    folder_id: Mapped[UUID | None] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"))
    recipient_email: Mapped[str | None] = mapped_column(String(320))
    request_id: Mapped[UUID | None] = mapped_column()
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    allow_download: Mapped[bool] = mapped_column(Boolean, nullable=False)
    max_downloads: Mapped[int | None] = mapped_column(Integer)
    download_grants: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
