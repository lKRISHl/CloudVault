from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.api.folders import WorkspaceUser
from app.api.users import Database
from app.schemas.permissions import (
    CandidatePage,
    GrantUpdate,
    OwnershipUpdate,
    PermissionPage,
    VisibilityUpdate,
)
from app.services.permissions import PermissionService

router = APIRouter()
Kind = Literal["files", "folders"]


@router.put("/{kind}/{resource_id}/group-permissions/{group_id}", status_code=204)
async def group_grant(
    kind: Kind,
    resource_id: UUID,
    group_id: UUID,
    payload: GrantUpdate,
    actor: WorkspaceUser,
    db: Database,
    request: Request,
):
    await PermissionService(db).group_grant(
        actor,
        kind,
        resource_id,
        group_id,
        payload.role,
        request.client.host if request.client else "",
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/{kind}/{resource_id}/permission-candidates", response_model=CandidatePage)
async def candidates(
    kind: Kind,
    resource_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    response: Response,
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0, le=10000),
):
    response.headers["Cache-Control"] = "no-store"
    return await PermissionService(db).candidates(actor, kind, resource_id, q, offset)


@router.post("/{kind}/{resource_id}/ownership", status_code=204)
async def transfer(
    kind: Kind,
    resource_id: UUID,
    payload: OwnershipUpdate,
    actor: WorkspaceUser,
    db: Database,
    request: Request,
):
    await PermissionService(db).transfer(
        actor, kind, resource_id, payload.user_id, request.client.host if request.client else ""
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/{kind}/{resource_id}/permissions", response_model=PermissionPage)
async def listing(
    kind: Kind,
    resource_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    response: Response,
    offset: int = Query(0, ge=0, le=10000),
):
    response.headers["Cache-Control"] = "no-store"
    return await PermissionService(db).listing(actor, kind, resource_id, offset)


@router.patch("/{kind}/{resource_id}/permissions", status_code=204)
async def visibility(
    kind: Kind,
    resource_id: UUID,
    payload: VisibilityUpdate,
    actor: WorkspaceUser,
    db: Database,
    request: Request,
):
    await PermissionService(db).visibility(
        actor, kind, resource_id, payload.visibility, request.client.host if request.client else ""
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.put("/{kind}/{resource_id}/permissions/{user_id}", status_code=204)
async def grant(
    kind: Kind,
    resource_id: UUID,
    user_id: UUID,
    payload: GrantUpdate,
    actor: WorkspaceUser,
    db: Database,
    request: Request,
):
    await PermissionService(db).grant(
        actor,
        kind,
        resource_id,
        user_id,
        payload.role,
        request.client.host if request.client else "",
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
