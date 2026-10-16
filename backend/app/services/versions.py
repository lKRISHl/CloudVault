from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.core.config import settings
from app.models import File, FileVersion, FileVersionChange, VersionPart
from app.models.file_version import CONTENT_FIELDS
from app.schemas.versions import VersionDownload, VersionPage, VersionRead, VersionTicket
from app.services.accounts import AccountService
from app.services.downloads import DownloadService
from app.services.files import FileService
from app.services.permissions import PermissionService
from app.services.uploads import utc
from app.storage.base import ObjectNotFoundError, ObjectRef, StorageError


class VersionService:
    def __init__(self, db, storage=None):
        self.db, self.storage = db, storage
        self.files = FileService(db)

    async def access(self, actor, file_id, write=False):
        role = await self.files.folders.authorize(actor, write=write)
        file = await self.db.scalar(
            select(File)
            .where(
                File.id == file_id,
                File.tenant_id == actor.tenant_id,
            )
            .execution_options(populate_existing=True)
        )
        if file is None:
            raise HTTPException(404, "File not found")
        await self.files.require_read(actor, role, file)
        if file.status != "uploaded":
            raise HTTPException(409, "Finish the original upload first")
        if write:
            if not PermissionService.writes(actor, role, file):
                raise HTTPException(403, "File write access required")
            path = await self.files.folders.ancestors(actor, file.folder_id)
            if path:
                await self.files.folders.require_write(actor, role, path[-1])
        return file, role

    @staticmethod
    def read(version, file, actor):
        return VersionRead(
            **{
                key: getattr(version, key)
                for key in (
                    "id",
                    "number",
                    "created_by",
                    "created_at",
                    "completed_at",
                    "status",
                    "size_bytes",
                    "declared_size_bytes",
                    "checksum_sha256",
                    "checksum_kind",
                    "scan_status",
                    "scanned_at",
                )
            },
            is_current=version.status == "uploaded" and version.number == file.current_version,
            expires_at=utc(version.upload_expires_at),
            upload_method=version.upload_method,
            multipart_state=version.multipart_state,
            part_size=version.multipart_part_size,
            cancelled_at=version.cancelled_at,
            prune_requested_at=version.prune_requested_at,
            prune_not_before=version.prune_not_before,
            can_complete=version.status == "pending"
            and version.cleaned_at is None
            and version.cancelled_at is None
            and version.created_by == actor.id
            and version.base_generation == file.version_generation
            and utc(version.upload_expires_at)
            + timedelta(seconds=settings.UPLOAD_COMPLETION_GRACE_SECONDS)
            > datetime.now(UTC),
        )

    async def find(self, actor, file, version_id):
        version = await self.db.scalar(
            select(FileVersion)
            .where(
                FileVersion.id == version_id,
                FileVersion.file_id == file.id,
                FileVersion.tenant_id == actor.tenant_id,
            )
            .execution_options(populate_existing=True)
        )
        if version is None or version.cleaned_at or version.purged_at or version.prune_requested_at:
            raise HTTPException(404, "Version not found")
        return version

    async def listing(self, actor, file_id, offset):
        file, role = await self.access(actor, file_id)
        visible = (
            FileVersion.tenant_id == actor.tenant_id,
            FileVersion.file_id == file.id,
            FileVersion.cleaned_at.is_(None),
            FileVersion.purged_at.is_(None),
            or_(FileVersion.status == "uploaded", FileVersion.created_by == actor.id),
        )
        rows = list(
            await self.db.scalars(
                select(FileVersion)
                .where(*visible)
                .order_by(FileVersion.number.desc())
                .offset(offset)
                .limit(26)
            )
        )
        retained = await self.db.scalar(
            select(func.coalesce(func.sum(FileVersion.size_bytes), 0)).where(
                FileVersion.tenant_id == actor.tenant_id,
                FileVersion.file_id == file.id,
                FileVersion.status == "uploaded",
                FileVersion.purged_at.is_(None),
            )
        )
        pending = await self.db.scalar(
            select(func.coalesce(func.sum(FileVersion.declared_size_bytes), 0)).where(
                FileVersion.tenant_id == actor.tenant_id,
                FileVersion.file_id == file.id,
                FileVersion.status == "pending",
                FileVersion.cleaned_at.is_(None),
            )
        )
        return VersionPage(
            file=self.files.read(actor, role, file),
            items=[self.read(row, file, actor) for row in rows[:25]],
            offset=offset,
            has_more=len(rows) > 25,
            retained_bytes=retained,
            pending_bytes=pending,
        )

    async def ticket(self, actor, file, version):
        if (
            version.cancelled_at
            or version.cleaned_at
            or version.prune_requested_at
            or version.purged_at
        ):
            raise HTTPException(410, "Version no longer available")
        if version.status == "uploaded":
            return VersionTicket(
                version=self.read(version, file, actor), expires_at=utc(version.upload_expires_at)
            )
        remaining = int((utc(version.upload_expires_at) - datetime.now(UTC)).total_seconds())
        if remaining < 1 or version.cleaned_at:
            raise HTTPException(410, "Version upload expired; start again")
        if version.base_generation != file.version_generation:
            raise HTTPException(409, "Current version changed; refresh and start again")
        try:
            signed = await self.storage.presign_upload(
                ObjectRef(file.tenant_id, file.id, version.object_id),
                version.declared_size_bytes,
                version.expected_checksum_sha256,
                remaining,
            )
        except StorageError:
            raise HTTPException(503, "Cannot authorize version upload") from None
        return VersionTicket(
            version=self.read(version, file, actor),
            upload_url=signed.url,
            headers=signed.headers,
            expires_at=utc(version.upload_expires_at),
        )

    async def start(self, actor, file_id, payload, ip):
        file, version = await self.reserve(actor, file_id, payload, ip)
        result = await self.ticket(actor, file, version)
        await self.db.commit()
        return result

    async def reserve(self, actor, file_id, payload, ip, multipart=False):
        await AccountService(self.db).limit("version-upload", ip, str(actor.id))
        file, _ = await self.access(actor, file_id, True)
        if payload.declared_size_bytes > (
            settings.MULTIPART_MAX_BYTES if multipart else settings.UPLOAD_MAX_BYTES
        ):
            raise HTTPException(413, "Replacement exceeds transfer size limit")
        version = await self.db.scalar(
            select(FileVersion).where(
                FileVersion.tenant_id == actor.tenant_id,
                FileVersion.created_by == actor.id,
                FileVersion.request_id == payload.request_id,
            )
        )
        if version:
            if (
                version.file_id != file.id
                or version.base_generation != payload.base_generation
                or version.declared_size_bytes != payload.declared_size_bytes
                or version.declared_content_type != payload.declared_content_type
                or version.expected_checksum_sha256 != payload.checksum_sha256
                or version.upload_method != ("multipart" if multipart else "basic")
                or (multipart and version.multipart_part_size != payload.part_size)
            ):
                raise HTTPException(409, "Request ID belongs to another version declaration")
        else:
            if file.version_generation != payload.base_generation:
                raise HTTPException(409, "Current version changed; refresh and start again")
            if multipart and payload.part_size != settings.MULTIPART_PART_BYTES:
                raise HTTPException(409, "Chunk configuration changed; refresh upload settings")
            pending = await self.db.scalar(
                select(func.count())
                .select_from(FileVersion)
                .where(
                    FileVersion.file_id == file.id,
                    FileVersion.status == "pending",
                    FileVersion.cleaned_at.is_(None),
                )
            )
            if pending >= 10:
                raise HTTPException(409, "Too many pending versions; wait for cleanup")
            number = await self.db.scalar(
                select(func.max(FileVersion.number)).where(FileVersion.file_id == file.id)
            )
            version = FileVersion(
                tenant_id=actor.tenant_id,
                file_id=file.id,
                number=(number or 1) + 1,
                base_generation=payload.base_generation,
                created_by=actor.id,
                request_id=payload.request_id,
                object_id=uuid4(),
                storage_bucket=settings.S3_BUCKET_NAME,
                upload_expires_at=datetime.now(UTC)
                + timedelta(
                    seconds=settings.MULTIPART_UPLOAD_SECONDS
                    if multipart
                    else settings.UPLOAD_URL_SECONDS
                ),
                declared_size_bytes=payload.declared_size_bytes,
                declared_content_type=payload.declared_content_type,
                expected_checksum_sha256=payload.checksum_sha256,
                status="pending",
                upload_method="multipart" if multipart else "basic",
                checksum_kind="sha256-composite" if multipart else "sha256",
                multipart_state="initializing" if multipart else None,
                multipart_part_size=payload.part_size if multipart else None,
                multipart_count=len(payload.checksums) if multipart else None,
            )
            self.db.add(version)
            await self.db.flush()
            if multipart:
                for index, checksum in enumerate(payload.checksums):
                    self.db.add(
                        VersionPart(
                            version_id=version.id,
                            number=index + 1,
                            size_bytes=min(
                                payload.part_size,
                                payload.declared_size_bytes - index * payload.part_size,
                            ),
                            checksum_sha256=checksum,
                        )
                    )
                await self.db.flush()
        if version.storage_bucket != settings.S3_BUCKET_NAME:
            raise HTTPException(503, "Version storage configuration changed")
        if (
            version.cancelled_at
            or version.cleaned_at
            or version.prune_requested_at
            or version.purged_at
        ):
            raise HTTPException(410, "Version no longer available")
        return file, version

    async def activate(self, actor, file, version, reason):
        for key in CONTENT_FIELDS:
            setattr(file, key, getattr(version, key))
        file.current_version = version.number
        file.version_generation += 1
        file.updated_at = datetime.now(UTC)
        self.db.add(
            FileVersionChange(
                tenant_id=file.tenant_id,
                file_id=file.id,
                number=version.number,
                generation=file.version_generation,
                actor_id=actor.id,
                reason=reason,
            )
        )
        await PermissionService(self.db).invalidate_shares(actor, "files", file.id)
        from app.services.version_policy import apply_policy

        await apply_policy(self.db, file)

    async def complete(self, actor, file_id, version_id, ip):
        method = await self.db.scalar(
            select(FileVersion.upload_method).where(
                FileVersion.id == version_id,
                FileVersion.file_id == file_id,
                FileVersion.tenant_id == actor.tenant_id,
            )
        )
        if method == "multipart":
            from app.services.version_multipart import VersionMultipartService

            return await VersionMultipartService(self.db, self.storage, file_id).complete(
                actor, version_id, ip
            )
        await AccountService(self.db).limit("version-complete", ip, str(actor.id))
        file, role = await self.access(actor, file_id, True)
        version = await self.find(actor, file, version_id)
        if version.cancelled_at:
            raise HTTPException(410, "Version upload cancelled")
        if version.created_by != actor.id:
            raise HTTPException(403, "Only the version uploader can complete it")
        if version.status == "uploaded":
            return self.files.read(actor, role, file)
        if version.base_generation != file.version_generation:
            raise HTTPException(409, "Current version changed; refresh and start again")
        if utc(version.upload_expires_at) + timedelta(
            seconds=settings.UPLOAD_COMPLETION_GRACE_SECONDS
        ) < datetime.now(UTC):
            raise HTTPException(410, "Version upload expired")
        if version.storage_bucket != settings.S3_BUCKET_NAME:
            raise HTTPException(503, "Version storage configuration changed")
        try:
            info = await self.storage.inspect_upload(
                ObjectRef(file.tenant_id, file.id, version.object_id)
            )
        except ObjectNotFoundError:
            raise HTTPException(409, "Version bytes have not arrived") from None
        except StorageError:
            raise HTTPException(503, "Cannot verify version bytes") from None
        if (
            info.size_bytes != version.declared_size_bytes
            or info.checksum_sha256 != version.expected_checksum_sha256
            or info.content_type != "application/octet-stream"
            or not info.etag
        ):
            raise HTTPException(409, "Version bytes do not match the declaration")
        version.status = "uploaded"
        version.size_bytes, version.checksum_sha256 = info.size_bytes, info.checksum_sha256
        version.content_type, version.storage_etag, version.completed_at = (
            info.content_type,
            info.etag,
            datetime.now(UTC),
        )
        await self.activate(actor, file, version, "upload")
        await self.db.commit()
        await self.db.refresh(file)
        return self.files.read(actor, role, file)

    async def cancel(self, actor, file_id, version_id, ip):
        await AccountService(self.db).limit("version-cancel", ip, str(actor.id))
        file, _ = await self.access(actor, file_id, True)
        version = await self.find(actor, file, version_id)
        if version.created_by != actor.id:
            raise HTTPException(403, "Only the version uploader can cancel it")
        if version.status == "uploaded":
            raise HTTPException(409, "Completed versions cannot be cancelled")
        version.cancelled_at = version.cancelled_at or datetime.now(UTC)
        if version.upload_method == "multipart":
            version.multipart_state = "aborted"
        await self.db.commit()  # Durable cancellation wins before any provider effect.
        if version.upload_method == "multipart":
            try:
                ref = ObjectRef(file.tenant_id, file.id, version.object_id)
                for upload_id in await self.storage.pending_for_object(ref):
                    await self.storage.abort_multipart(ref, upload_id)
            except StorageError:
                pass  # Original deadline/cleanup references still protect every exact key.
        return {"detail": "Cancellation recorded; storage cleanup follows the original deadline"}

    async def retry(self, actor, file_id, version_id, checksum, ip):
        await AccountService(self.db).limit("version-upload", ip, str(actor.id))
        file, _ = await self.access(actor, file_id, True)
        version = await self.find(actor, file, version_id)
        if version.created_by != actor.id:
            raise HTTPException(403, "Only the version uploader can retry it")
        if version.upload_method != "basic" or version.expected_checksum_sha256 != checksum:
            raise HTTPException(409, "Reselect the original basic-upload content")
        result = await self.ticket(actor, file, version)
        await self.db.commit()
        return result

    async def checked(self, actor, file, version):
        if version.status != "uploaded":
            raise HTTPException(409, "Version is not complete")
        snapshot = SimpleNamespace(
            id=file.id,
            tenant_id=file.tenant_id,
            name=file.name,
            **{key: getattr(version, key) for key in CONTENT_FIELDS},
        )
        url = await DownloadService(self.db, self.storage).checked_url(
            snapshot, settings.DOWNLOAD_URL_SECONDS
        )
        await self.access(actor, file.id)
        return url

    async def download(self, actor, file_id, version_id, ip):
        await AccountService(self.db).limit("download-grant", ip, str(actor.id))
        file, _ = await self.access(actor, file_id)
        version = await self.find(actor, file, version_id)
        issued = datetime.now(UTC)
        url = await self.checked(actor, file, version)
        return VersionDownload(
            download_url=url, expires_at=issued + timedelta(seconds=settings.DOWNLOAD_URL_SECONDS)
        )

    async def restore(self, actor, file_id, version_id, generation, ip):
        await AccountService(self.db).limit("version-restore", ip, str(actor.id))
        file, role = await self.access(actor, file_id, True)
        if generation != file.version_generation:
            raise HTTPException(409, "Current version changed; refresh before restoring")
        version = await self.find(actor, file, version_id)
        await self.checked(actor, file, version)
        # access() refreshes the same identity under the tenant write lock.
        if file.current_version != version.number:
            await self.activate(actor, file, version, "restore")
        await self.db.commit()
        await self.db.refresh(file)
        return self.files.read(actor, role, file)
