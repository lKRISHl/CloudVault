from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class ShareCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_in_hours: int = Field(default=24, ge=1, le=720)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    allow_download: bool = True
    max_downloads: int | None = Field(default=None, ge=1, le=10000)
    recipient_email: EmailStr | None = None
    request_id: UUID | None = None
    token: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{43}$")

    @model_validator(mode="after")
    def retry_pair(self):
        if (self.request_id is None) != (self.token is None):
            raise ValueError("request_id and client-generated token must be supplied together")
        return self


class ShareRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    file_id: UUID | None
    folder_id: UUID | None = None
    recipient_email: str | None = None
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
    folder_id: UUID | None = None
    file_id: UUID | None = None
    offset: int = Field(default=0, ge=0, le=10000)


class SharedEntry(BaseModel):
    id: UUID
    name: str
    kind: str
    size_bytes: int | None = None


class SharedFolder(BaseModel):
    name: str
    folder_id: UUID
    items: list[SharedEntry]
    offset: int
    has_more: bool
    expires_at: datetime
    allow_download: bool
    grants_remaining: int | None


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
