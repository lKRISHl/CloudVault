"""Durable preview intent and retained derivative identity; never stores content bytes."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PreviewJob(Base):
    __tablename__ = "preview_jobs"
    __table_args__ = (
        CheckConstraint("reserved_bytes BETWEEN 0 AND 1048576", name="ck_preview_quota_bytes"),
        UniqueConstraint("tenant_id", "requested_by", "request_id", name="uq_preview_request"),
        CheckConstraint(
            "state IN ('queued','running','ready','failed','cancelled')", name="ck_preview_state"
        ),
        CheckConstraint(
            "attempts BETWEEN 0 AND 3 AND page BETWEEN 0 AND 99", name="ck_preview_bounds"
        ),
        Index("ix_preview_dispatch", "state", "next_attempt_at", "lease_until"),
        Index("ix_preview_cleanup", "cleanup_after", "checked_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column()
    file_id: Mapped[UUID] = mapped_column()
    version_id: Mapped[UUID] = mapped_column()
    requested_by: Mapped[UUID] = mapped_column()
    request_id: Mapped[UUID] = mapped_column()
    generation: Mapped[int] = mapped_column(Integer)  # Zero means explicit historical version.
    page: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_id: Mapped[UUID | None] = mapped_column()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cleanup_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleanup_failed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    artifact_id: Mapped[UUID] = mapped_column(default=uuid4)
    storage_bucket: Mapped[str] = mapped_column(String(63))
    namespace: Mapped[str] = mapped_column(String(64))
    digest: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    reserved_bytes: Mapped[int] = mapped_column(
        BigInteger, default=1048576, server_default="1048576"
    )
    cleaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
