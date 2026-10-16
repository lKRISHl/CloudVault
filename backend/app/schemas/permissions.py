from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VisibilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visibility: Literal["workspace", "private"]


class GrantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["viewer", "editor"] | None


class GrantRead(BaseModel):
    user_id: UUID
    role: Literal["viewer", "editor"]
    full_name: str = ""
    email: str = ""


class GroupGrantRead(BaseModel):
    group_id: UUID
    name: str
    role: Literal["viewer", "editor"]


class PermissionPage(BaseModel):
    name: str
    owner_id: UUID
    owner_name: str = ""
    visibility: Literal["workspace", "private"]
    items: list[GrantRead]
    group_items: list[GroupGrantRead] = Field(default_factory=list)
    offset: int
    has_more: bool


class CandidateRead(BaseModel):
    user_id: UUID
    full_name: str
    email: str


class CandidatePage(BaseModel):
    items: list[CandidateRead]
    offset: int
    has_more: bool


class OwnershipUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
