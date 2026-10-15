from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.api.folders import WorkspaceUser
from app.api.multipart import router as multipart_router
from app.api.storage import UploadStorage
from app.api.users import Database
from app.api.versions import router as versions_router
from app.schemas.downloads import DownloadTicket
from app.schemas.files import FileMove, FilePage, FileRead
from app.schemas.folders import FolderName
from app.schemas.search import FileSearchPage, FileSearchQuery
from app.schemas.trash import DiscardMetadataRequest
from app.schemas.uploads import UploadConfiguration, UploadProof, UploadStart, UploadTicket
from app.services.downloads import DownloadService
from app.services.files import FileService
from app.services.search import FileSearchService
from app.services.uploads import UploadService

router = APIRouter()
router.include_router(multipart_router)
router.include_router(versions_router)


@router.post("/{file_id}/move", response_model=FileRead)
async def move(
    file_id: UUID, payload: FileMove, actor: WorkspaceUser, db: Database, request: Request
):
    return await FileService(db).move(
        actor, file_id, payload, request.client.host if request.client else ""
    )


@router.post("/{file_id}/discard-metadata", status_code=204)
async def discard(
    file_id: UUID,
    payload: DiscardMetadataRequest,
    actor: WorkspaceUser,
    db: Database,
    request: Request,
):
    await FileService(db).discard_legacy(
        actor, file_id, request.client.host if request.client else ""
    )
    return Response(status_code=204)


@router.patch("/{file_id}", response_model=FileRead)
async def rename(
    file_id: UUID, payload: FolderName, actor: WorkspaceUser, db: Database, request: Request
):
    return await FileService(db).rename(
        actor, file_id, payload.name, request.client.host if request.client else ""
    )


@router.get("/search", response_model=FileSearchPage)
async def search(
    actor: WorkspaceUser,
    db: Database,
    query: Annotated[FileSearchQuery, Query()],
    response: Response,
    request: Request,
):
    response.headers["Cache-Control"] = "no-store"
    return await FileSearchService(db).search(
        actor, query, request.client.host if request.client else ""
    )


@router.get("/upload-configuration", response_model=UploadConfiguration)
async def upload_configuration(actor: WorkspaceUser, db: Database):
    return await UploadService(db).configuration(actor)


@router.post("/uploads", response_model=UploadTicket, status_code=201)
async def start_upload(
    payload: UploadStart,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    response: Response,
    request: Request,
):
    response.headers["Cache-Control"] = "no-store"
    return await UploadService(db, storage).start(
        actor, payload, request.client.host if request.client else ""
    )


@router.post("/{file_id}/upload-url", response_model=UploadTicket)
async def retry_upload(
    file_id: UUID,
    payload: UploadProof,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    response: Response,
    request: Request,
):
    response.headers["Cache-Control"] = "no-store"
    return await UploadService(db, storage).retry(
        actor, file_id, payload.checksum_sha256, request.client.host if request.client else ""
    )


@router.post("/{file_id}/complete", response_model=FileRead)
async def complete_upload(
    file_id: UUID, actor: WorkspaceUser, db: Database, storage: UploadStorage, request: Request
):
    return await UploadService(db, storage).complete(
        actor, file_id, request.client.host if request.client else ""
    )


@router.get("", response_model=FilePage)
async def children(
    actor: WorkspaceUser,
    db: Database,
    folder_id: UUID | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
):
    return await FileService(db).children(actor, folder_id, offset, limit)


@router.post("/{file_id}/download-url", response_model=DownloadTicket)
async def download_url(
    file_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    response: Response,
    request: Request,
):
    response.headers["Cache-Control"] = "no-store"
    return await DownloadService(db, storage).ticket(
        actor, file_id, request.client.host if request.client else ""
    )


@router.get("/{file_id}", response_model=FileRead)
async def details(file_id: UUID, actor: WorkspaceUser, db: Database):
    return await FileService(db).details(actor, file_id)
