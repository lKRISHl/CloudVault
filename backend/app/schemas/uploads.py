import base64
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.files import FileMetadataCreate, FileRead


class UploadProof(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checksum_sha256: str = Field(min_length=44, max_length=44)

    @field_validator("checksum_sha256")
    @classmethod
    def checksum(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except ValueError as error:
            raise ValueError("Use a base64 SHA-256 checksum") from error
        if len(decoded) != 32 or base64.b64encode(decoded).decode() != value:
            raise ValueError("Use a canonical base64 SHA-256 checksum")
        return value


class UploadStart(FileMetadataCreate, UploadProof):
    request_id: UUID


class UploadTicket(BaseModel):
    file: FileRead
    upload_url: str
    headers: dict[str, str]
    expires_at: datetime


class UploadConfiguration(BaseModel):
    max_bytes: int
    enabled: bool
    multipart_max_bytes: int = 0
    multipart_part_size: int = 8 * 1024 * 1024
