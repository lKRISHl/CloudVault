from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.api.folders import WorkspaceUser
from app.api.storage import ShareStorageFactory
from app.api.users import Database
from app.schemas.shares import (
    ShareAccess,
    ShareCreate,
    ShareCreated,
    SharedDownload,
    SharedFile,
    SharePage,
)
from app.services.shares import ShareService

router = APIRouter()


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


@router.post("/files/{file_id}/shares", response_model=ShareCreated, status_code=201)
async def create(
    file_id: UUID,
    payload: ShareCreate,
    actor: WorkspaceUser,
    db: Database,
    request: Request,
    response: Response,
):
    no_store(response)
    return await ShareService(db).create(
        actor, file_id, payload, request.client.host if request.client else ""
    )


@router.get("/files/{file_id}/shares", response_model=SharePage)
async def listing(
    file_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    response: Response,
    offset: int = Query(0, ge=0, le=10000),
):
    no_store(response)
    return await ShareService(db).listing(actor, file_id, offset)


@router.delete("/files/{file_id}/shares/{link_id}", status_code=204)
async def revoke(
    file_id: UUID, link_id: UUID, actor: WorkspaceUser, db: Database, request: Request
):
    await ShareService(db).revoke(
        actor, file_id, link_id, request.client.host if request.client else ""
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/shares/access", response_model=SharedFile)
async def access(payload: ShareAccess, db: Database, request: Request, response: Response):
    no_store(response)
    return await ShareService(db).access(payload, request.client.host if request.client else "")


@router.post("/shares/download-url", response_model=SharedDownload)
async def download(
    payload: ShareAccess,
    db: Database,
    storage: ShareStorageFactory,
    request: Request,
    response: Response,
):
    no_store(response)
    return await ShareService(db, storage_factory=storage).access(
        payload, request.client.host if request.client else "", download=True
    )
