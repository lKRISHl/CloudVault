from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.folders import FolderName


class GroupName(FolderName):
    pass


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str


class GroupPage(BaseModel):
    items: list[GroupRead]
    offset: int
    has_more: bool


class GroupMembershipUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    present: bool = Field(strict=True)
