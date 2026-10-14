from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.files import FileMetadataCreate, FileRead
from app.schemas.uploads import UploadProof


class MultipartStart(FileMetadataCreate):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    part_size: int = Field(ge=5242880, le=33554432, strict=True)
    checksums: list[str] = Field(min_length=1, max_length=1024)

    @field_validator("checksums")
    @classmethod
    def digests(cls, values):
        return [UploadProof(checksum_sha256=value).checksum_sha256 for value in values]


class PartTicket(BaseModel):
    number: int
    size_bytes: int
    checksum_sha256: str
    confirmed: bool
    expires_at: datetime | None = None
    upload_url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class MultipartTicket(BaseModel):
    file: FileRead
    part_size: int
    parts: list[PartTicket]
    expires_at: datetime
