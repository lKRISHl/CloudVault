from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.api.folders import WorkspaceUser
from app.api.users import Database
from app.schemas.groups import GroupMembershipUpdate, GroupName, GroupPage, GroupRead
from app.schemas.permissions import CandidatePage
from app.services.groups import GroupService

router = APIRouter()


@router.get("", response_model=GroupPage)
async def listing(
    actor: WorkspaceUser,
    db: Database,
    response: Response,
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0, le=10000),
):
    response.headers["Cache-Control"] = "no-store"
    return await GroupService(db).listing(actor, q, offset)


@router.post("", response_model=GroupRead, status_code=201)
async def create(
    payload: GroupName, actor: WorkspaceUser, db: Database, request: Request, response: Response
):
    response.headers["Cache-Control"] = "no-store"
    return await GroupService(db).create(
        actor, payload.name, request.client.host if request.client else ""
    )


@router.get("/{group_id}/members", response_model=CandidatePage)
async def members(
    group_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    response: Response,
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0, le=10000),
    candidates: bool = False,
):
    response.headers["Cache-Control"] = "no-store"
    return await GroupService(db).members(actor, group_id, q, offset, candidates=candidates)


@router.put("/{group_id}/members/{user_id}", status_code=204)
async def membership(
    group_id: UUID,
    user_id: UUID,
    payload: GroupMembershipUpdate,
    actor: WorkspaceUser,
    db: Database,
    request: Request,
):
    await GroupService(db).membership(
        actor, group_id, user_id, payload.present, request.client.host if request.client else ""
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.delete("/{group_id}", status_code=204)
async def remove(group_id: UUID, actor: WorkspaceUser, db: Database, request: Request):
    await GroupService(db).remove(actor, group_id, request.client.host if request.client else "")
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
