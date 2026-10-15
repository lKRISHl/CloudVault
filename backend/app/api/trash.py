from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.api.folders import WorkspaceUser
from app.api.users import Database
from app.schemas.trash import CancelTrashRequest, PurgeRequest, RestoreRequest, TrashPage, TrashRead
from app.services.trash import TrashService

router = APIRouter()


@router.post(
    "/folders/{resource_id}/cancel-uploads-and-trash", response_model=TrashRead, status_code=201
)
async def cancel_and_trash(
    resource_id: UUID,
    payload: CancelTrashRequest,
    actor: WorkspaceUser,
    db: Database,
    request: Request,
):
    return await TrashService(db).move_to_trash(
        actor,
        "folders",
        resource_id,
        request.client.host if request.client else "",
        cancel_uploads=True,
    )


@router.post("/{kind}/{resource_id}/trash", response_model=TrashRead, status_code=201)
async def move(
    kind: Literal["files", "folders"],
    resource_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    request: Request,
):
    return await TrashService(db).move_to_trash(
        actor, kind, resource_id, request.client.host if request.client else ""
    )


@router.get("/trash", response_model=TrashPage)
async def listing(actor: WorkspaceUser, db: Database, offset: int = Query(0, ge=0, le=10000)):
    return await TrashService(db).listing(actor, offset)


@router.post("/trash/{entry_id}/restore", status_code=204)
async def restore(
    entry_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    request: Request,
    payload: RestoreRequest | None = None,
):
    await TrashService(db).restore(
        actor, entry_id, request.client.host if request.client else "", payload
    )
    return Response(status_code=204)


@router.post("/trash/{entry_id}/purge", status_code=202)
async def purge(
    entry_id: UUID, payload: PurgeRequest, actor: WorkspaceUser, db: Database, request: Request
):
    await TrashService(db).purge(actor, entry_id, request.client.host if request.client else "")
    return {
        "detail": (
            "Permanent deletion queued; restoration disabled. "
            "Folder deletion includes nested trash."
        )
    }
