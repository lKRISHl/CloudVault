from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UploadPart(Base):
    __tablename__ = "upload_parts"
    __table_args__ = (
        CheckConstraint("number BETWEEN 1 AND 1024", name="ck_upload_parts_number"),
        CheckConstraint("size_bytes BETWEEN 1 AND 33554432", name="ck_upload_parts_size"),
        CheckConstraint(
            "(storage_etag IS NULL AND confirmed_at IS NULL) OR "
            "(storage_etag IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_upload_parts_receipt",
        ),
    )
    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum_sha256: Mapped[str] = mapped_column(String(44))
    storage_etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
