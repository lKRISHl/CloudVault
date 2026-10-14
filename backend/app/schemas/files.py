from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.folders import FolderName


class FileMetadataCreate(FolderName):
    """Pending metadata declaration, never proof of upload."""

    folder_id: UUID | None = None
    declared_size_bytes: int = Field(ge=0, le=9007199254740991, strict=True)
    declared_content_type: str | None = Field(
        default=None,
        max_length=255,
        pattern=r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$",
    )


class FileRead(BaseModel):
    id: UUID
    tenant_id: UUID
    folder_id: UUID | None
    created_by: UUID
    name: str
    declared_size_bytes: int
    declared_content_type: str | None
    status: Literal["pending", "uploaded"]
    upload_method: Literal["basic", "multipart"] = "basic"
    checksum_kind: Literal["sha256", "sha256-composite"] = "sha256"
    multipart_part_size: int | None = None
    multipart_count: int | None = None
    multipart_state: Literal["active", "completed", "aborted"] | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    content_type: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    can_write: bool


class FilePage(BaseModel):
    items: list[FileRead]
    offset: int
    limit: int
    has_more: bool
