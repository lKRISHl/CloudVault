"""Durable provider-creation intent, deliberately independent of file/account deletion."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UploadIntent(Base):
    __tablename__ = "upload_intents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "created_by", "request_id", name="uq_upload_intents_request"),
        Index("ix_upload_intents_cleanup", "storage_bucket", "expires_at", "checked_at"),
        Index("ix_upload_intents_folder", "tenant_id", "folder_id"),
    )
    file_id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column()
    object_id: Mapped[UUID] = mapped_column()
    created_by: Mapped[UUID] = mapped_column()
    request_id: Mapped[UUID] = mapped_column()
    storage_bucket: Mapped[str] = mapped_column(String(63))
    fingerprint: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Retained independently of hierarchy/account deletion; old intents have unknown scope.
    folder_id: Mapped[UUID | None] = mapped_column(nullable=True)
    scope_recorded: Mapped[bool] = mapped_column(Boolean, default=True, server_default=false())
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
