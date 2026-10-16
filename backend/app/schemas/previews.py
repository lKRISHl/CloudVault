from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: UUID | None = None
    page: int = Field(default=0, ge=0, le=99, strict=True)


class PreviewContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["image", "pdf", "video", "text", "unsupported"]
    detected_type: str | None = Field(default=None, max_length=100)
    image_base64: str | None = Field(default=None, max_length=1400000)
    text: str | None = Field(default=None, max_length=262144)
    reason: str | None = Field(default=None, max_length=200)
    width: int | None = Field(default=None, ge=1, le=1600)
    height: int | None = Field(default=None, ge=1, le=1600)
    page: int = Field(default=0, ge=0, le=99)
    pages: int = Field(default=1, ge=1, le=100)
    truncated: bool = False


class PreviewRead(PreviewContent):
    file_id: UUID
    version_id: UUID
    version_number: int
    name: str
    generation: int
    scan_status: Literal["clean"] = "clean"


class PreviewJobRequest(PreviewRequest):
    request_id: UUID


class PreviewJobRead(BaseModel):
    id: UUID
    state: Literal["queued", "running", "ready", "failed", "cancelled"]
    expires_at: datetime
    preview: PreviewRead | None = None
