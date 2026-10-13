from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole
from app.schemas.auth import TenantRead
from app.schemas.common import Name

AssignableRole = Literal["admin", "member"]


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: Name


class OrganizationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: AssignableRole


class InviteRequest(RoleUpdate):
    email: EmailStr


class MemberRead(BaseModel):
    user_id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    joined_at: datetime


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: EmailStr
    role: AssignableRole
    expires_at: datetime


class InvitationCreated(InvitationRead):
    token: str


class AcceptInvitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=128)
    full_name: Name
    password: str = Field(min_length=8, max_length=128)


class ExistingInvitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=128)


class OwnershipTransfer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    password: str = Field(min_length=1, max_length=128)
    confirmation: Literal["TRANSFER"]


class WorkspaceRead(BaseModel):
    tenant: TenantRead
    role: UserRole
