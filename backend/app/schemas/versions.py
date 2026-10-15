from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.files import FileRead
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
