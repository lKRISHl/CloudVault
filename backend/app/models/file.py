from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class File(Base):
    """Organization-owned metadata; pending records do not establish stored bytes."""

    __tablename__ = "files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["folder_id", "tenant_id"],
            ["folders.id", "folders.tenant_id"],
            name="fk_files_folder_tenant",
        ),
        CheckConstraint("declared_size_bytes >= 0", name="ck_files_declared_size"),
        CheckConstraint("status IN ('pending', 'uploaded')", name="ck_files_status"),
        CheckConstraint(
            "(object_id IS NULL AND storage_bucket IS NULL AND upload_expires_at IS NULL "
            "AND expected_checksum_sha256 IS NULL AND upload_request_id IS NULL) OR "
            "(object_id IS NOT NULL AND storage_bucket IS NOT NULL "
            "AND upload_expires_at IS NOT NULL "
            "AND expected_checksum_sha256 IS NOT NULL AND upload_request_id IS NOT NULL)",
            name="ck_files_upload_reference",
        ),
        CheckConstraint(
            "(status = 'pending' AND size_bytes IS NULL AND checksum_sha256 IS NULL "
            "AND content_type IS NULL AND storage_etag IS NULL AND completed_at IS NULL) OR "
            "(status = 'uploaded' AND object_id IS NOT NULL AND size_bytes IS NOT NULL "
            "AND size_bytes = declared_size_bytes AND checksum_sha256 IS NOT NULL "
            "AND checksum_sha256 = expected_checksum_sha256 "
            "AND content_type IS NOT NULL AND content_type = 'application/octet-stream' "
            "AND storage_etag IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="ck_files_verified_upload",
        ),
        CheckConstraint(
            "(upload_method = 'basic' AND checksum_kind = 'sha256' AND multipart_upload_id IS NULL "
            "AND multipart_part_size IS NULL AND multipart_count IS NULL AND multipart_s"
            "tate IS NULL) OR "
            "(upload_method = 'multipart' AND checksum_kind = 'sha256-composite' "
            "AND object_id IS NOT NULL AND multipart_upload_id IS NOT NULL "
            "AND length(multipart_upload_id) > 0 AND multipart_part_size IS NOT NULL "
            "AND multipart_part_size BETWEEN 5242880 AND 33554432 "
            "AND multipart_count IS NOT NULL AND multipart_count BETWEEN 1 AND 1024 "
            "AND multipart_state IS NOT NULL AND ((status = 'pending' AND multipart_stat"
            "e IN ('active','aborted')) "
            "OR (status = 'uploaded' AND multipart_state = 'completed')))",
            name="ck_files_transfer_mode",
        ),
        UniqueConstraint("storage_bucket", "object_id", name="uq_files_storage_object"),
        UniqueConstraint(
            "tenant_id", "created_by", "upload_request_id", name="uq_files_upload_request"
        ),
        UniqueConstraint("tenant_id", "folder_id", "name_key", name="uq_files_sibling_name"),
        Index(
            "uq_files_root_name",
            "tenant_id",
            "name_key",
            unique=True,
            postgresql_where=text("folder_id IS NULL"),
            sqlite_where=text("folder_id IS NULL"),
        ),
        Index("ix_files_children", "tenant_id", "folder_id", "name", "id"),
        Index("ix_files_creator", "tenant_id", "created_by"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    folder_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    name_key: Mapped[str] = mapped_column(String(768))
    declared_size_bytes: Mapped[int] = mapped_column(BigInteger)
    declared_content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending")
    object_id: Mapped[UUID | None] = mapped_column(nullable=True)
    storage_bucket: Mapped[str | None] = mapped_column(String(63), nullable=True)
    upload_request_id: Mapped[UUID | None] = mapped_column(nullable=True)
    upload_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expected_checksum_sha256: Mapped[str | None] = mapped_column(String(44), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(44), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    upload_method: Mapped[str] = mapped_column(String(16), default="basic", server_default="basic")
    checksum_kind: Mapped[str] = mapped_column(
        String(32), default="sha256", server_default="sha256"
    )
    multipart_upload_id: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    multipart_part_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    multipart_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    multipart_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
