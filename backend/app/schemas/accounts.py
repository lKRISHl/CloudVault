from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecoveryRequest(AccountRequest):
    email: EmailStr
    purpose: Literal["verify", "reset"]


class TokenRequest(AccountRequest):
    token: str = Field(min_length=32, max_length=128)


class ResetRequest(TokenRequest):
    password: str = Field(min_length=8, max_length=128)


class PasswordRequest(AccountRequest):
    password: str = Field(min_length=1, max_length=128)


class EmailChangeRequest(PasswordRequest):
    email: EmailStr


class ConfirmEmailRequest(TokenRequest, PasswordRequest):
    pass


class DeleteAccountRequest(PasswordRequest):
    confirmation: Literal["DELETE"]


class SessionRead(BaseModel):
    id: UUID
    created_at: datetime
    expires_at: datetime
    current: bool


class EmailDeliveryRead(BaseModel):
    id: UUID
    purpose: str
    state: str
    attempts: int
    next_attempt_at: datetime
