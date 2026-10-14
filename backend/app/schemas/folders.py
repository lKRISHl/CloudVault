import unicodedata
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FolderName(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value.strip())
        if (
            not value
            or value in (".", "..")
            or any(char in "/\\" or unicodedata.category(char) in ("Cc", "Cs") for char in value)
        ):
            raise ValueError(
                "Use a folder name without path separators, control characters or dot-only paths"
            )
        return value


class FolderCreate(FolderName):
    parent_id: UUID | None = None


class FolderMove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_id: UUID | None


class FolderRead(BaseModel):
    id: UUID
    tenant_id: UUID
    parent_id: UUID | None
    created_by: UUID
    name: str
    created_at: datetime
    updated_at: datetime
    can_write: bool


class FolderPage(BaseModel):
    parent: FolderRead | None
    breadcrumbs: list[FolderRead]
    items: list[FolderRead]
    offset: int
    limit: int
    has_more: bool
