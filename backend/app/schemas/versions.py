from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.files import FileRead
from app.schemas.multipart import MultipartResume, PartTicket
from app.schemas.uploads import UploadProof


class VersionStart(UploadProof):
    request_id: UUID
    base_generation: int = Field(ge=1, strict=True)
    declared_size_bytes: int = Field(ge=0, strict=True)
    declared_content_type: str | None = Field(
        default=None, max_length=255, pattern=r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$"
    )


class VersionRestore(BaseModel):
    base_generation: int = Field(ge=1, strict=True)


class VersionRead(BaseModel):
    scan_status: str = "pending"
    scanned_at: datetime | None = None
    upload_method: str = "basic"
    multipart_state: str | None = None
    part_size: int | None = None
    cancelled_at: datetime | None = None
    prune_requested_at: datetime | None = None
    prune_not_before: datetime | None = None
    id: UUID
    number: int
    created_by: UUID
    created_at: datetime
    completed_at: datetime | None
    status: str
    size_bytes: int | None
    declared_size_bytes: int
    checksum_sha256: str | None
    checksum_kind: str
    is_current: bool
    expires_at: datetime
    can_complete: bool


class VersionPage(BaseModel):
    file: FileRead
    items: list[VersionRead]
    offset: int
    has_more: bool
    retained_bytes: int
    pending_bytes: int


class VersionTicket(BaseModel):
    version: VersionRead
    upload_url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime


class VersionDownload(BaseModel):
    download_url: str
    expires_at: datetime


class VersionMultipartStart(VersionStart):
    part_size: int = Field(ge=5242880, le=33554432, strict=True)
    checksums: list[str] = Field(min_length=1, max_length=1024)

    @field_validator("checksums")
    @classmethod
    def digests(cls, values):
        return MultipartResume.digests(values)


class VersionMultipartTicket(BaseModel):
    version: VersionRead
    part_size: int
    parts: list[PartTicket]
    expires_at: datetime
    can_resume: bool
    confirmed_bytes: int


class VersionDelete(BaseModel):
    confirmation: Literal["DELETE"]


class VersionPolicy(BaseModel):
    keep_last: int | None = Field(default=None, ge=1, le=1000, strict=True)
    confirmation: Literal["PRUNE"]
