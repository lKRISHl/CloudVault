from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import bearer_scheme, get_current_user
from app.api.folders import WorkspaceUser
from app.api.storage import ShareStorageFactory
from app.api.users import Database
from app.schemas.shares import (
    ShareAccess,
    ShareCreate,
    ShareCreated,
    SharedDownload,
    SharedFile,
    SharedFolder,
    SharePage,
)
from app.services.shares import ShareService

router = APIRouter()


async def optional_recipient(
    request: Request,
    db: Database,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
):
    if credentials is None:
        return None
    user = await get_current_user(request, credentials, db)
    user._share_session_id = request.state.session_id
    user._share_tenant_id = user.tenant_id
    return user


Recipient = Annotated[object, Depends(optional_recipient)]


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


@router.post("/shares/access", response_model=SharedFile | SharedFolder)
async def access(
    payload: ShareAccess, db: Database, request: Request, response: Response, recipient: Recipient
):
    no_store(response)
    return await ShareService(db).access(
        payload, request.client.host if request.client else "", recipient=recipient
    )


@router.post("/shares/download-url", response_model=SharedDownload)
async def download(
    payload: ShareAccess,
    recipient: Recipient,
    db: Database,
    storage: ShareStorageFactory,
    request: Request,
    response: Response,
):
    no_store(response)
    return await ShareService(db, storage_factory=storage).access(
        payload, request.client.host if request.client else "", download=True, recipient=recipient
    )


@router.post("/folders/{folder_id}/shares", response_model=ShareCreated, status_code=201)
async def create_folder(
    folder_id: UUID,
    payload: ShareCreate,
    actor: WorkspaceUser,
    db: Database,
    request: Request,
    response: Response,
):
    no_store(response)
    return await ShareService(db).create(
        actor, folder_id, payload, request.client.host if request.client else "", kind="folders"
    )


@router.get("/folders/{folder_id}/shares", response_model=SharePage)
async def folder_links(
    folder_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    response: Response,
    offset: int = Query(0, ge=0, le=10000),
):
    no_store(response)
    return await ShareService(db).listing(actor, folder_id, offset, kind="folders")


@router.delete("/folders/{folder_id}/shares/{link_id}", status_code=204)
async def revoke_folder(
    folder_id: UUID, link_id: UUID, actor: WorkspaceUser, db: Database, request: Request
):
    await ShareService(db).revoke(
        actor, folder_id, link_id, request.client.host if request.client else "", kind="folders"
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/shares/folder", response_model=SharedFolder)
async def browse_folder(
    payload: ShareAccess, recipient: Recipient, db: Database, request: Request, response: Response
):
    no_store(response)
    return await ShareService(db).access(
        payload, request.client.host if request.client else "", recipient=recipient, browse=True
    )
