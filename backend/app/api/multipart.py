from uuid import UUID

from fastapi import APIRouter, Path, Request, Response

from app.api.folders import WorkspaceUser
from app.api.storage import UploadStorage
from app.api.users import Database
from app.schemas.files import FileRead
from app.schemas.multipart import (
    MultipartProgress,
    MultipartResume,
    MultipartStart,
    MultipartTicket,
    PartTicket,
)
from app.services.multipart import MultipartService

router = APIRouter()


@router.post("/{file_id}/multipart/progress", response_model=MultipartProgress)
async def progress(
    file_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    response: Response,
    request: Request,
):
    response.headers["Cache-Control"] = "no-store"
    return await MultipartService(db, storage).progress(
        actor, file_id, request.client.host if request.client else ""
    )


@router.post("/{file_id}/multipart/resume", response_model=MultipartTicket)
async def resume(
    file_id: UUID,
    payload: MultipartResume,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    response: Response,
    request: Request,
):
    response.headers["Cache-Control"] = "no-store"
    return await MultipartService(db, storage).resume(
        actor, file_id, payload, request.client.host if request.client else ""
    )


@router.post("/multipart/uploads", response_model=MultipartTicket, status_code=201)
async def start(
    payload: MultipartStart,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    response: Response,
    request: Request,
):
    response.headers["Cache-Control"] = "no-store"
    return await MultipartService(db, storage).start(
        actor, payload, request.client.host if request.client else ""
    )


@router.post("/{file_id}/multipart/parts/{number}/url", response_model=PartTicket)
async def part_url(
    file_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    response: Response,
    request: Request,
    number: int = Path(ge=1, le=1024),
):
    response.headers["Cache-Control"] = "no-store"
    return await MultipartService(db, storage).part_url(
        actor, file_id, number, request.client.host if request.client else ""
    )


@router.post("/{file_id}/multipart/parts/{number}/confirm", response_model=PartTicket)
async def confirm(
    file_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    request: Request,
    number: int = Path(ge=1, le=1024),
):
    return await MultipartService(db, storage).confirm(
        actor, file_id, number, request.client.host if request.client else ""
    )


@router.post("/{file_id}/multipart/complete", response_model=FileRead)
async def complete(
    file_id: UUID, actor: WorkspaceUser, db: Database, storage: UploadStorage, request: Request
):
    return await MultipartService(db, storage).complete(
        actor, file_id, request.client.host if request.client else ""
    )


@router.post("/{file_id}/multipart/abort", response_model=FileRead)
async def abort(
    file_id: UUID, actor: WorkspaceUser, db: Database, storage: UploadStorage, request: Request
):
    return await MultipartService(db, storage).abort(
        actor, file_id, request.client.host if request.client else ""
    )
