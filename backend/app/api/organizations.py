from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.deps import get_verified_user
from app.api.users import Database
from app.core.security import set_refresh_cookie
from app.models import Tenant, User
from app.schemas.auth import TenantRead, TokenResponse
from app.schemas.organizations import (
    AcceptInvitation,
    InvitationCreated,
    InvitationRead,
    InviteRequest,
    MemberRead,
    OrganizationUpdate,
    RoleUpdate,
)
from app.services.accounts import AccountService
from app.services.organizations import OrganizationService

router = APIRouter()
CurrentUser = Annotated[User, Depends(get_verified_user)]


@router.get("/current", response_model=TenantRead)
async def organization(actor: CurrentUser) -> Tenant:
    return actor.tenant


@router.patch("/current", response_model=TenantRead)
async def rename(payload: OrganizationUpdate, actor: CurrentUser, db: Database) -> Tenant:
    return await OrganizationService(db).rename(actor, payload.name)


@router.get("/current/members", response_model=list[MemberRead])
async def members(
    actor: CurrentUser,
    db: Database,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[MemberRead]:
    return await OrganizationService(db).members(actor, limit, offset)


@router.patch("/current/members/{user_id}", response_model=MemberRead)
async def change_role(user_id: UUID, payload: RoleUpdate, actor: CurrentUser, db: Database):
    return await OrganizationService(db).change_role(actor, user_id, payload.role)


@router.delete("/current/members/{user_id}", status_code=204)
async def remove_member(user_id: UUID, actor: CurrentUser, db: Database) -> None:
    await OrganizationService(db).remove_member(actor, user_id)


@router.post("/current/invitations", response_model=InvitationCreated, status_code=201)
async def invite(payload: InviteRequest, actor: CurrentUser, request: Request, db: Database):
    await AccountService(db).limit(
        "invitations", request.client.host if request.client else "unknown", str(actor.id)
    )
    return await OrganizationService(db).invite(actor, payload)


@router.get("/current/invitations", response_model=list[InvitationRead])
async def invitations(
    actor: CurrentUser,
    db: Database,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await OrganizationService(db).invitations(actor, limit, offset)


@router.delete("/current/invitations/{invitation_id}", status_code=204)
async def revoke(invitation_id: UUID, actor: CurrentUser, db: Database) -> None:
    await OrganizationService(db).revoke_invitation(actor, invitation_id)


@router.post("/invitations/accept", response_model=TokenResponse, status_code=201)
async def accept(payload: AcceptInvitation, response: Response, request: Request, db: Database):
    await AccountService(db).limit(
        "account-links", request.client.host if request.client else "unknown"
    )
    session = await OrganizationService(db).accept(payload)
    set_refresh_cookie(response, session.refresh_token)
    return session.to_response()
