from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ShareCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_in_hours: int = Field(default=24, ge=1, le=720)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    allow_download: bool = True
    max_downloads: int | None = Field(default=None, ge=1, le=10000)


class ShareRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    file_id: UUID
    created_by: UUID
    expires_at: datetime
    revoked_at: datetime | None
    allow_download: bool
    max_downloads: int | None
    download_grants: int
    created_at: datetime
    password_required: bool


class ShareCreated(ShareRead):
    share_url: str


class SharePage(BaseModel):
    file_name: str
    items: list[ShareRead]
    offset: int
    has_more: bool


class ShareAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    password: str = Field(default="", max_length=128)


class SharedFile(BaseModel):
    name: str
    size_bytes: int
    expires_at: datetime
    allow_download: bool
    grants_remaining: int | None


class SharedDownload(BaseModel):
    download_url: str
    expires_at: datetime
    name: str
