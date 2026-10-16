"""Strict, bounded subscriptions. Clients never select a tenant or another principal."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.search import FileSearchQuery


class LiveTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9:_-]+$")
    kind: Literal[
        "folders",
        "files",
        "file",
        "version",
        "versions",
        "members",
        "invitations",
        "workspaces",
        "trash",
        "permissions",
        "shares",
        "search",
        "preview",
    ]
    resource_id: UUID | None = None
    job_id: UUID | None = None
    version_id: UUID | None = None
    parent_id: UUID | None = None
    resource_kind: Literal["files", "folders"] | None = None
    offset: int = Field(default=0, ge=0, le=10000, strict=True)
    search: FileSearchQuery | None = None

    @model_validator(mode="after")
    def coherent(self):
        needs_resource = self.kind in (
            "file",
            "version",
            "versions",
            "permissions",
            "shares",
            "preview",
        )
        if needs_resource != (self.resource_id is not None):
            raise ValueError("Invalid resource subscription")
        if (self.kind == "preview") != (self.job_id is not None):
            raise ValueError("Invalid preview subscription")
        if (self.kind == "version") != (self.version_id is not None):
            raise ValueError("Invalid version subscription")
        if self.kind == "permissions" and self.resource_kind is None:
            raise ValueError("Invalid permission subscription")
        if self.resource_kind is not None and self.kind not in ("permissions", "shares"):
            raise ValueError("Invalid permission subscription")
        if self.parent_id is not None and self.kind not in ("files", "folders"):
            raise ValueError("Parent not supported")
        if (self.kind == "search") != (self.search is not None):
            raise ValueError("Invalid search subscription")
        return self


class LiveSubscribe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["subscribe"]
    topics: list[LiveTopic] = Field(max_length=8)

    @model_validator(mode="after")
    def unique_keys(self):
        if len({topic.key for topic in self.topics}) != len(self.topics):
            raise ValueError("Duplicate subscription key")
        return self


class LiveHello(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["authenticate"]
    ticket: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")
