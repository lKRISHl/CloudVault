from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.api.folders import WorkspaceUser
from app.api.storage import UploadStorage
from app.api.users import Database
from app.schemas.files import FileRead
from app.schemas.multipart import MultipartResume, PartTicket
from app.schemas.uploads import UploadProof
from app.schemas.versions import (
    VersionDelete,
    VersionDownload,
    VersionMultipartStart,
    VersionMultipartTicket,
    VersionPage,
    VersionPolicy,
    VersionRestore,
    VersionStart,
    VersionTicket,
)
from app.services.version_multipart import VersionMultipartService
from app.services.version_policy import VersionPolicyService
from app.services.versions import VersionService

router = APIRouter()


@router.post("/{file_id}/versions/{version_id}/scan", status_code=202)
async def retry_scan(
    file_id: UUID, version_id: UUID, actor: WorkspaceUser, db: Database, request: Request
):
    from app.services.scans import ScanService

    return await ScanService(db).retry(
        actor, file_id, version_id, request.client.host if request.client else ""
    )


@router.post("/{file_id}/versions/{version_id}/upload-url", response_model=VersionTicket)
async def retry(
    file_id: UUID,
    version_id: UUID,
    payload: UploadProof,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    request: Request,
):
    return await VersionService(db, storage).retry(
        actor,
        file_id,
        version_id,
        payload.checksum_sha256,
        request.client.host if request.client else "",
    )


@router.post(
    "/{file_id}/versions/multipart", response_model=VersionMultipartTicket, status_code=201
)
async def multipart_start(
    file_id: UUID,
    payload: VersionMultipartStart,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    request: Request,
):
    return await VersionMultipartService(db, storage, file_id).start(
        actor, payload, request.client.host if request.client else ""
    )


@router.get("/{file_id}/versions/{version_id}/progress", response_model=VersionMultipartTicket)
async def progress(
    file_id: UUID,
    version_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    request: Request,
):
    return await VersionMultipartService(db, storage, file_id).progress(
        actor, version_id, request.client.host if request.client else ""
    )


@router.post("/{file_id}/versions/{version_id}/resume", response_model=VersionMultipartTicket)
async def resume(
    file_id: UUID,
    version_id: UUID,
    payload: MultipartResume,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    request: Request,
):
    return await VersionMultipartService(db, storage, file_id).resume(
        actor, version_id, payload, request.client.host if request.client else ""
    )


@router.post("/{file_id}/versions/{version_id}/parts/{number}/url", response_model=PartTicket)
async def part_url(
    file_id: UUID,
    version_id: UUID,
    number: int,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    request: Request,
):
    return await VersionMultipartService(db, storage, file_id).part_url(
        actor, version_id, number, request.client.host if request.client else ""
    )


@router.post("/{file_id}/versions/{version_id}/parts/{number}/confirm", response_model=PartTicket)
async def confirm(
    file_id: UUID,
    version_id: UUID,
    number: int,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    request: Request,
):
    return await VersionMultipartService(db, storage, file_id).confirm(
        actor, version_id, number, request.client.host if request.client else ""
    )


@router.post("/{file_id}/versions/{version_id}/cancel", status_code=202)
async def cancel(
    file_id: UUID,
    version_id: UUID,
    actor: WorkspaceUser,
    db: Database,
    storage: UploadStorage,
    request: Request,
):
    return await VersionService(db, storage).cancel(
        actor, file_id, version_id, request.client.host if request.client else ""
    )


@router.post("/{file_id}/versions/{version_id}/prune", status_code=202)
async def prune(
    file_id: UUID,
    version_id: UUID,
    payload: VersionDelete,
    actor: WorkspaceUser,
    db: Database,
    request: Request,
):
    return await VersionPolicyService(db).prune(
        actor, file_id, version_id, request.client.host if request.client else ""
    )


@router.put("/{file_id}/version-policy", response_model=FileRead)
async def policy(
    file_id: UUID, payload: VersionPolicy, actor: WorkspaceUser, db: Database, request: Request
):
    return await VersionPolicyService(db).configure(
        actor, file_id, payload.keep_last, request.client.host if request.client else ""
    )


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
