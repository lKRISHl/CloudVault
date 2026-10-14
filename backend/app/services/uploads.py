from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import File, User
from app.schemas.files import FileMetadataCreate, FileRead
from app.schemas.uploads import UploadConfiguration, UploadStart, UploadTicket
from app.services.accounts import AccountService
from app.services.files import FileService
from app.storage.base import ObjectNotFoundError, ObjectRef, ObjectStorage, StorageError


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class UploadService:
    def __init__(self, db: AsyncSession, storage: ObjectStorage | None = None):
        self.db, self.storage = db, storage
        self.files = FileService(db)

    async def configuration(self, actor: User) -> UploadConfiguration:
        await self.files.folders.authorize(actor)
        return UploadConfiguration(
            max_bytes=settings.UPLOAD_MAX_BYTES,
            enabled=bool(settings.S3_BUCKET_NAME),
            multipart_max_bytes=settings.MULTIPART_MAX_BYTES,
            multipart_part_size=settings.MULTIPART_PART_BYTES,
        )

    async def owned_file(self, actor: User, file_id: UUID) -> File:
        file = await self.db.scalar(
            select(File)
            .where(
                File.id == file_id,
                File.tenant_id == actor.tenant_id,
                File.upload_cleanup_at.is_(None),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if file is None:
            raise HTTPException(status_code=404, detail="File not found")
        if file.upload_method != "basic":
            raise HTTPException(status_code=409, detail="Use multipart controls for this upload")
        if file.created_by != actor.id:
            raise HTTPException(
                status_code=403, detail="Only the upload creator can complete or retry this upload"
            )
        if not file.object_id:
            raise HTTPException(status_code=409, detail="This metadata has no upload session")
        if file.storage_bucket != settings.S3_BUCKET_NAME:
            raise HTTPException(status_code=503, detail="Upload storage configuration changed")
        return file

    async def parent_authority(self, actor, role, file):
        path = await self.files.folders.ancestors(actor, file.folder_id)
        if path:
            self.files.folders.require_write(actor, role, path[-1])

    async def ticket(self, actor, role, file) -> UploadTicket:
        if file.status != "pending":
            raise HTTPException(status_code=409, detail="This file has already been uploaded")
        remaining = int((utc(file.upload_expires_at) - datetime.now(UTC)).total_seconds())
        if remaining <= 0:
            raise HTTPException(status_code=410, detail="Upload authorization expired")
        grant = await self.storage.presign_upload(
            ObjectRef(actor.tenant_id, file.id, file.object_id),
            file.declared_size_bytes,
            file.expected_checksum_sha256,
            remaining,
        )
        return UploadTicket(
            file=self.files.read(actor, role, file),
            upload_url=grant.url,
            headers=grant.headers,
            expires_at=utc(file.upload_expires_at),
        )

    async def start(self, actor: User, payload: UploadStart, ip: str = "") -> UploadTicket:
        if payload.declared_size_bytes > settings.UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds the basic upload size limit")
        await AccountService(self.db).limit("upload-grant", ip, str(actor.id))
        role = await self.files.folders.authorize(actor, write=True)
        existing = await self.db.scalar(
            select(File).where(
                File.tenant_id == actor.tenant_id,
                File.created_by == actor.id,
                File.upload_request_id == payload.request_id,
            )
        )
        try:
            if existing:
                if existing.upload_cleanup_at is not None:
                    raise HTTPException(410, "Upload expired and was cleaned; start a new upload")
                if any(
                    (
                        existing.name != payload.name,
                        existing.folder_id != payload.folder_id,
                        existing.declared_size_bytes != payload.declared_size_bytes,
                        existing.declared_content_type != payload.declared_content_type,
                        existing.expected_checksum_sha256 != payload.checksum_sha256,
                    )
                ):
                    raise HTTPException(
                        status_code=409, detail="Upload request ID belongs to different metadata"
                    )
                await self.owned_file(actor, existing.id)
                await self.parent_authority(actor, role, existing)
                result = await self.ticket(actor, role, existing)
            else:
                metadata = FileMetadataCreate(
                    **payload.model_dump(include=FileMetadataCreate.model_fields.keys())
                )
                file = await self.files.allocate(actor, role, metadata)
                file.object_id, file.storage_bucket = uuid4(), settings.S3_BUCKET_NAME
                file.upload_request_id = payload.request_id
                file.expected_checksum_sha256 = payload.checksum_sha256
                file.upload_expires_at = datetime.now(UTC) + timedelta(
                    seconds=settings.UPLOAD_URL_SECONDS
                )
                await self.db.flush()
                result = await self.ticket(actor, role, file)
            await self.db.commit()
            return result
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(status_code=409, detail="Upload metadata conflict") from None
        except StorageError:
            await self.db.rollback()
            raise HTTPException(status_code=503, detail="Upload storage is unavailable") from None

    async def retry(self, actor: User, file_id: UUID, checksum: str, ip: str = "") -> UploadTicket:
        await AccountService(self.db).limit("upload-grant", ip, str(actor.id))
        role = await self.files.folders.authorize(actor, write=True)
        file = await self.owned_file(actor, file_id)
        await self.parent_authority(actor, role, file)
        if file.expected_checksum_sha256 != checksum:
            raise HTTPException(
                status_code=409, detail="Choose the same file content to retry this upload"
            )
        try:
            result = await self.ticket(actor, role, file)
            await self.db.commit()
            return result
        except StorageError:
            raise HTTPException(status_code=503, detail="Upload storage is unavailable") from None

    async def complete(self, actor: User, file_id: UUID, ip: str = "") -> FileRead:
        await AccountService(self.db).limit("upload-complete", ip, str(actor.id))
        role = await self.files.folders.authorize(actor, write=True)
        file = await self.owned_file(actor, file_id)
        await self.parent_authority(actor, role, file)
        if file.status == "uploaded":
            return self.files.read(actor, role, file)
        deadline = utc(file.upload_expires_at) + timedelta(
            seconds=settings.UPLOAD_COMPLETION_GRACE_SECONDS
        )
        if datetime.now(UTC) > deadline:
            raise HTTPException(status_code=410, detail="Upload completion deadline expired")
        try:
            info = await self.storage.inspect_upload(
                ObjectRef(actor.tenant_id, file.id, file.object_id)
            )
        except ObjectNotFoundError:
            raise HTTPException(
                status_code=409,
                detail="Upload object is missing; transfer the file before completing",
            ) from None
        except StorageError:
            raise HTTPException(status_code=503, detail="Upload storage is unavailable") from None
        if (
            info.size_bytes != file.declared_size_bytes
            or info.checksum_sha256 != file.expected_checksum_sha256
            or info.content_type != "application/octet-stream"
        ):
            raise HTTPException(
                status_code=409, detail="Stored object does not match the upload declaration"
            )
        file.status, file.size_bytes = "uploaded", info.size_bytes
        file.checksum_sha256, file.content_type = info.checksum_sha256, info.content_type
        file.storage_etag, file.completed_at = info.etag, datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(file)
        return self.files.read(actor, role, file)
