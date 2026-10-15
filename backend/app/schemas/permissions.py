from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VisibilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visibility: Literal["workspace", "private"]


class GrantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["viewer", "editor"] | None


class GrantRead(BaseModel):
    user_id: UUID
    role: Literal["viewer", "editor"]


class PermissionPage(BaseModel):
    name: str
    visibility: Literal["workspace", "private"]
    items: list[GrantRead]
    offset: int
    has_more: bool
