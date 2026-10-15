from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import File, User
from app.schemas.downloads import DownloadTicket
from app.services.accounts import AccountService
from app.services.files import FileService
from app.storage.base import ObjectNotFoundError, ObjectRef, ObjectStorage, StorageError


class DownloadService:
    def __init__(self, db: AsyncSession, storage: ObjectStorage):
        self.db, self.storage = db, storage
        self.files = FileService(db)

    async def ticket(self, actor: User, file_id: UUID, ip: str) -> DownloadTicket:
        await AccountService(self.db).limit("download-grant", ip, str(actor.id))
        role = await self.files.folders.authorize(actor)
        file = await self.db.scalar(
            select(File).where(File.id == file_id, File.tenant_id == actor.tenant_id)
        )
        if file is None:
            raise HTTPException(status_code=404, detail="File not found")
        if file.status != "uploaded" or not file.object_id:
            raise HTTPException(status_code=409, detail="File is not ready for download")
        await self.files.folders.ancestors(actor, file.folder_id)
        issued = datetime.now(UTC)
        url = await self.checked_url(file, settings.DOWNLOAD_URL_SECONDS, actor)
        role = await self.files.folders.authorize(actor)
        return DownloadTicket(
            file=self.files.read(actor, role, file),
            download_url=url,
            expires_at=issued + timedelta(seconds=settings.DOWNLOAD_URL_SECONDS),
        )

    async def checked_url(
        self, file: File, ttl: int, actor: User | None = None, deadline: datetime | None = None
    ) -> str:
        """Caller establishes authority; reuse verified object checks for share grants."""
        if file.storage_bucket != settings.S3_BUCKET_NAME:
            raise HTTPException(status_code=503, detail="Download storage configuration changed")
        ref = ObjectRef(file.tenant_id, file.id, file.object_id)
        try:
            info = await self.storage.inspect_upload(ref)
            if (
                info.size_bytes != file.size_bytes
                or info.checksum_sha256
                != (
                    f"{file.checksum_sha256}-{file.multipart_count}"
                    if file.checksum_kind == "sha256-composite"
                    else file.checksum_sha256
                )
                or info.etag != file.storage_etag
                or info.content_type != "application/octet-stream"
            ):
                raise HTTPException(
                    status_code=409, detail="Stored file no longer matches verification"
                )
            # Membership is authoritative, including changes during the provider inspection.
            if actor is not None:
                await self.files.folders.authorize(actor)
            if deadline is not None:
                ttl = min(ttl, int((deadline - datetime.now(UTC)).total_seconds()))
                if ttl < 1:
                    raise HTTPException(404, "Share unavailable or credentials incorrect")
            url = await self.storage.presign_download(ref, file.name, ttl)
            if actor is not None:
                await self.files.folders.authorize(actor)
        except ObjectNotFoundError:
            raise HTTPException(status_code=409, detail="Stored file is unavailable") from None
        except StorageError:
            raise HTTPException(status_code=503, detail="Cannot authorize download") from None
        return url
