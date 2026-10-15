from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
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

# Exact immutable content metadata. Names, ACLs and locations belong to the logical file.
CONTENT_FIELDS = (
    "object_id",
    "storage_bucket",
    "upload_expires_at",
    "declared_size_bytes",
    "declared_content_type",
    "expected_checksum_sha256",
    "size_bytes",
    "checksum_sha256",
    "content_type",
    "storage_etag",
    "completed_at",
    "upload_method",
    "checksum_kind",
    "multipart_upload_id",
    "multipart_part_size",
    "multipart_count",
    "multipart_state",
)


class FileVersion(Base):
    __tablename__ = "file_versions"
    __table_args__ = (
        UniqueConstraint("file_id", "number", name="uq_file_versions_number"),
        UniqueConstraint("tenant_id", "created_by", "request_id", name="uq_file_versions_request"),
        UniqueConstraint("storage_bucket", "object_id", name="uq_file_versions_object"),
        CheckConstraint("number >= 1 AND declared_size_bytes >= 0", name="ck_file_versions_size"),
        CheckConstraint("status IN ('pending', 'uploaded')", name="ck_file_versions_status"),
        CheckConstraint("cancelled_at IS NULL OR status = 'pending'", name="ck_versions_cancelled"),
        CheckConstraint(
            "(prune_requested_at IS NULL AND prune_not_before IS NULL) OR "
            "(status = 'uploaded' AND prune_requested_at IS NOT NULL "
            "AND prune_not_before IS NOT NULL)",
            name="ck_versions_prune",
        ),
        CheckConstraint(
            "status = 'pending' OR (size_bytes = declared_size_bytes AND size_bytes IS NOT NULL "
            "AND checksum_sha256 = expected_checksum_sha256 AND checksum_sha256 IS NOT NULL "
            "AND content_type = 'application/octet-stream' AND content_type IS NOT NULL "
            "AND storage_etag IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_file_versions_verified",
        ),
        Index("ix_file_versions_history", "tenant_id", "file_id", "number"),
        Index("ix_file_versions_cleanup", "status", "checked_at", "upload_expires_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    file_id: Mapped[UUID] = mapped_column(ForeignKey("files.id"))
    number: Mapped[int] = mapped_column(Integer)
    base_generation: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(16), default="pending")
    object_id: Mapped[UUID] = mapped_column()
    storage_bucket: Mapped[str] = mapped_column(String(63))
    upload_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    declared_size_bytes: Mapped[int] = mapped_column(BigInteger)
    declared_content_type: Mapped[str | None] = mapped_column(String(255))
    expected_checksum_sha256: Mapped[str] = mapped_column(String(44))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(String(44))
    content_type: Mapped[str | None] = mapped_column(String(255))
    storage_etag: Mapped[str | None] = mapped_column(String(255))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    upload_method: Mapped[str] = mapped_column(String(16), default="basic")
    checksum_kind: Mapped[str] = mapped_column(String(32), default="sha256")
    multipart_upload_id: Mapped[str | None] = mapped_column(String(1024))
    multipart_part_size: Mapped[int | None] = mapped_column(Integer)
    multipart_count: Mapped[int | None] = mapped_column(Integer)
    multipart_state: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cleaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prune_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prune_not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VersionPart(Base):
    __tablename__ = "version_parts"
    __table_args__ = (
        CheckConstraint("number BETWEEN 1 AND 1024", name="ck_version_parts_number"),
        CheckConstraint("size_bytes BETWEEN 1 AND 33554432", name="ck_version_parts_size"),
        CheckConstraint(
            "(storage_etag IS NULL AND confirmed_at IS NULL) OR "
            "(storage_etag IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_version_parts_receipt",
        ),
    )
    version_id: Mapped[UUID] = mapped_column(ForeignKey("file_versions.id"), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum_sha256: Mapped[str] = mapped_column(String(44))
    storage_etag: Mapped[str | None] = mapped_column(String(255))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FileVersionChange(Base):
    __tablename__ = "file_version_changes"
    __table_args__ = (Index("ix_version_changes_file", "tenant_id", "file_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    file_id: Mapped[UUID] = mapped_column(ForeignKey("files.id"))
    number: Mapped[int] = mapped_column(Integer)
    generation: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
