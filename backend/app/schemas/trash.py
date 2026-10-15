from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
