import unicodedata
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.files import FilePage, FileRead


class FileSearchItem(FileRead):
    folder_name: str | None = None


class FileSearchPage(FilePage):
    items: list[FileSearchItem]


class FileSearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(default="", max_length=128)
    scope: Literal["workspace", "root", "folder"] = "workspace"
    folder_id: UUID | None = None
    status: Literal["pending", "uploaded"] | None = None
    upload_method: Literal["basic", "multipart"] | None = None
    created_by: UUID | None = None
    declared_content_type: str | None = Field(
        default=None, max_length=255, pattern=r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$"
    )
    min_bytes: int | None = Field(default=None, ge=0, le=9007199254740991)
    max_bytes: int | None = Field(default=None, ge=0, le=9007199254740991)
    sort: Literal["name", "size", "created_at", "updated_at"] = "name"
    direction: Literal["asc", "desc"] = "asc"
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=25, ge=1, le=100)

    @field_validator("q")
    @classmethod
    def normalize_query(cls, value):
        if any(unicodedata.category(char) in ("Cc", "Cs") for char in value):
            raise ValueError("Search cannot contain control characters")
        return unicodedata.normalize("NFC", value.strip())

    @model_validator(mode="after")
    def coherent_filters(self):
        if (self.scope == "folder") != (self.folder_id is not None):
            raise ValueError("Choose a folder only when scope is folder")
        if (
            self.min_bytes is not None
            and self.max_bytes is not None
            and self.min_bytes > self.max_bytes
        ):
            raise ValueError("Minimum size cannot exceed maximum size")
        return self
