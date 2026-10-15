from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.api.folders import WorkspaceUser
from app.api.storage import UploadStorage
from app.api.users import Database
from app.schemas.files import FileRead
from app.schemas.versions import (
    VersionDownload,
    VersionPage,
    VersionRestore,
    VersionStart,
    VersionTicket,
)
from app.services.versions import VersionService

router = APIRouter()


@router.get("/{file_id}/versions", response_model=VersionPage)
async def listing(
    file_id: UUID, actor: WorkspaceUser, db: Database, offset: int = Query(0, ge=0, le=10000)
):
    return await VersionService(db).listing(actor, file_id, offset)


@router.post("/{file_id}/versions", response_model=VersionTicket, status_code=201)
async def start(
    file_id: UUID,
    payload: VersionStart,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    request: Request,
):
    return await VersionService(db, storage).start(
        actor, file_id, payload, request.client.host if request.client else ""
    )


@router.post("/{file_id}/versions/{version_id}/complete", response_model=FileRead)
async def complete(
    file_id: UUID,
    version_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    request: Request,
):
    return await VersionService(db, storage).complete(
        actor, file_id, version_id, request.client.host if request.client else ""
    )


@router.post("/{file_id}/versions/{version_id}/download-url", response_model=VersionDownload)
async def download(
    file_id: UUID,
    version_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    request: Request,
):
    return await VersionService(db, storage).download(
        actor, file_id, version_id, request.client.host if request.client else ""
    )


@router.post("/{file_id}/versions/{version_id}/restore", response_model=FileRead)
async def restore(
    file_id: UUID,
    version_id: UUID,
    payload: VersionRestore,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    request: Request,
):
    return await VersionService(db, storage).restore(
        actor,
        file_id,
        version_id,
        payload.base_generation,
        request.client.host if request.client else "",
    )
