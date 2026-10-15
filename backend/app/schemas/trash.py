from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.folders import FolderName


class TrashRead(BaseModel):
    id: UUID
    resource_id: UUID
    kind: Literal["files", "folders"]
    name: str
    trashed_at: datetime
    retain_until: datetime
    not_before: datetime
    purge_requested_at: datetime | None


class TrashPage(BaseModel):
    items: list[TrashRead]
    offset: int
    has_more: bool


class PurgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["DELETE"]


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    use_original: bool = True
    destination_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        return FolderName.validate_name(value) if value is not None else None


class CancelTrashRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["CANCEL UPLOADS"]


class DiscardMetadataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["DISCARD"]
