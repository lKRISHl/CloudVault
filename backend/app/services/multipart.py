import base64
import hashlib
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import File, UploadPart, User
from app.schemas.files import FileMetadataCreate
from app.schemas.multipart import MultipartStart, MultipartTicket, PartTicket
from app.services.accounts import AccountService
from app.services.files import FileService
from app.services.uploads import utc
from app.storage.base import ObjectNotFoundError, ObjectRef, ObjectStorage, StorageError


class MultipartService:
    def __init__(self, db: AsyncSession, storage: ObjectStorage):
        self.db, self.storage, self.files = db, storage, FileService(db)

    async def limit(self, actor, ip, category, part=False):
        options = {"max_identity": 4096, "max_ip": 16384} if part else {}
        await AccountService(self.db).limit(category, ip, str(actor.id), **options)

    @staticmethod
    def ref(file):
        return ObjectRef(file.tenant_id, file.id, file.object_id)

    async def own(self, actor, file_id):
        role = await self.files.folders.authorize(actor, write=True)
        file = await self.db.scalar(
            select(File)
            .where(File.id == file_id, File.tenant_id == actor.tenant_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if file is None:
            raise HTTPException(404, "File not found")
        if file.created_by != actor.id:
            raise HTTPException(403, "Only the upload creator can manage multipart uploads")
        if file.upload_method != "multipart":
            raise HTTPException(409, "This file does not use multipart upload")
        if file.storage_bucket != settings.S3_BUCKET_NAME:
            raise HTTPException(503, "Upload storage configuration changed")
        path = await self.files.folders.ancestors(actor, file.folder_id)
        if path:
            self.files.folders.require_write(actor, role, path[-1])
        return file, role

    @staticmethod
    def active(file, grace=False):
        if file.multipart_state != "active":
            raise HTTPException(409, "Multipart upload is no longer active")
        deadline = utc(file.upload_expires_at) + timedelta(
            seconds=settings.UPLOAD_COMPLETION_GRACE_SECONDS if grace else 0
        )
        if datetime.now(UTC) > deadline:
            raise HTTPException(410, "Multipart upload authorization expired")

    async def parts(self, file):
        return list(
            await self.db.scalars(
                select(UploadPart).where(UploadPart.file_id == file.id).order_by(UploadPart.number)
            )
        )

    async def part(self, file, number):
        part = await self.db.get(UploadPart, (file.id, number))
        if part is None:
            raise HTTPException(404, "Part not found")
        return part

    async def grant(self, file, part):
        remaining = min(
            settings.UPLOAD_URL_SECONDS,
            int((utc(file.upload_expires_at) - datetime.now(UTC)).total_seconds()),
        )
        if remaining <= 0:
            raise HTTPException(410, "Multipart upload authorization expired")
        signed = await self.storage.presign_part(
            self.ref(file),
            file.multipart_upload_id,
            part.number,
            part.size_bytes,
            part.checksum_sha256,
            remaining,
        )
        return PartTicket(
            number=part.number,
            size_bytes=part.size_bytes,
            checksum_sha256=part.checksum_sha256,
            confirmed=part.confirmed_at is not None,
            upload_url=signed.url,
            expires_at=datetime.now(UTC) + timedelta(seconds=remaining),
            headers=signed.headers,
        )

    async def ticket(self, actor, role, file):
        receipts = await self.parts(file)
        grants = []
        if file.status != "uploaded":
            self.active(file)
            for part in receipts:
                if part.confirmed_at:
                    grants.append(
                        PartTicket(
                            number=part.number,
                            size_bytes=part.size_bytes,
                            checksum_sha256=part.checksum_sha256,
                            confirmed=True,
                        )
                    )
                else:
                    grants.append(await self.grant(file, part))
        return MultipartTicket(
            file=self.files.read(actor, role, file),
            part_size=file.multipart_part_size,
            parts=grants,
            expires_at=utc(file.upload_expires_at),
        )

    async def start(self, actor: User, payload: MultipartStart, ip=""):
        size = payload.declared_size_bytes
        if size <= 0 or size > settings.MULTIPART_MAX_BYTES:
            raise HTTPException(
                413,
                "File exceeds the multipart limit or is empty; use basic upload for empty files",
            )
        count = (size + payload.part_size - 1) // payload.part_size
        if count != len(payload.checksums) or count > 1024:
            raise HTTPException(422, "Part declarations do not match the file size")
        digest = base64.b64encode(
            hashlib.sha256(
                b"".join(base64.b64decode(value) for value in payload.checksums)
            ).digest()
        ).decode()
        await self.limit(actor, ip, "multipart-start")
        role = await self.files.folders.authorize(actor, write=True)
        existing = await self.db.scalar(
            select(File).where(
                File.tenant_id == actor.tenant_id,
                File.created_by == actor.id,
                File.upload_request_id == payload.request_id,
            )
        )
        created = None
        try:
            if existing:
                if (
                    existing.upload_method != "multipart"
                    or existing.name != payload.name
                    or existing.folder_id != payload.folder_id
                    or existing.declared_size_bytes != size
                    or existing.declared_content_type != payload.declared_content_type
                    or existing.multipart_part_size != payload.part_size
                    or existing.expected_checksum_sha256 != digest
                ):
                    raise HTTPException(409, "Upload request ID belongs to different metadata")
                path = await self.files.folders.ancestors(actor, existing.folder_id)
                if path:
                    self.files.folders.require_write(actor, role, path[-1])
                if existing.storage_bucket != settings.S3_BUCKET_NAME:
                    raise HTTPException(503, "Upload storage configuration changed")
                file = existing
            else:
                if payload.part_size != settings.MULTIPART_PART_BYTES:
                    raise HTTPException(
                        409, "Upload chunk configuration changed; refresh upload settings"
                    )
                file = await self.files.allocate(
                    actor,
                    role,
                    FileMetadataCreate(
                        **payload.model_dump(include=FileMetadataCreate.model_fields.keys())
                    ),
                )
                file.id, file.object_id, file.storage_bucket = (
                    uuid4(),
                    uuid4(),
                    settings.S3_BUCKET_NAME,
                )
                file.upload_request_id, file.expected_checksum_sha256 = payload.request_id, digest
                file.upload_expires_at = datetime.now(UTC) + timedelta(
                    seconds=settings.MULTIPART_UPLOAD_SECONDS
                )
                file.upload_method, file.checksum_kind, file.multipart_state = (
                    "multipart",
                    "sha256-composite",
                    "active",
                )
                file.multipart_part_size, file.multipart_count = payload.part_size, count
                file.multipart_upload_id = await self.storage.create_multipart(self.ref(file))
                created = (self.ref(file), file.multipart_upload_id)
                await self.db.flush()
                for index, checksum in enumerate(payload.checksums):
                    self.db.add(
                        UploadPart(
                            file_id=file.id,
                            number=index + 1,
                            size_bytes=min(payload.part_size, size - index * payload.part_size),
                            checksum_sha256=checksum,
                        )
                    )
                await self.db.flush()
            result = await self.ticket(actor, role, file)
            await self.db.commit()
            return result
        except (StorageError, SQLAlchemyError) as error:
            await self.db.rollback()
            if created:
                with suppress(StorageError):
                    await self.storage.abort_multipart(*created)  # Orphans require Phase 9 cleanup.
            raise HTTPException(
                409 if isinstance(error, IntegrityError) else 503, "Multipart initialization failed"
            ) from None
        except HTTPException:
            await self.db.rollback()
            if created:
                with suppress(StorageError):
                    await self.storage.abort_multipart(*created)
            raise

    async def part_url(self, actor, file_id, number, ip=""):
        await self.limit(actor, ip, "multipart-part-grant", True)
        file, _ = await self.own(actor, file_id)
        self.active(file)
        try:
            return await self.grant(file, await self.part(file, number))
        except StorageError:
            raise HTTPException(503, "Cannot authorize upload part") from None

    @staticmethod
    def check_part(declaration, actual):
        if (
            declaration.number != actual.number
            or declaration.size_bytes != actual.size_bytes
            or declaration.checksum_sha256 != actual.checksum_sha256
        ):
            raise HTTPException(409, "Stored part does not match its declaration")
        if not actual.etag:
            raise HTTPException(409, "Stored part has no verified receipt")

    async def confirm(self, actor, file_id, number, ip=""):
        await self.limit(actor, ip, "multipart-confirm", True)
        file, _ = await self.own(actor, file_id)
        self.active(file, grace=True)
        part = await self.part(file, number)
        try:
            actual = await self.storage.inspect_part(
                self.ref(file), file.multipart_upload_id, number
            )
        except ObjectNotFoundError:
            raise HTTPException(409, "Upload part has not arrived") from None
        except StorageError:
            raise HTTPException(503, "Cannot verify upload part") from None
        self.check_part(part, actual)
        part.storage_etag, part.confirmed_at = actual.etag, datetime.now(UTC)
        await self.db.commit()
        return PartTicket(
            number=part.number,
            size_bytes=part.size_bytes,
            checksum_sha256=part.checksum_sha256,
            confirmed=True,
        )

    async def existing_object(self, file):
        try:
            return await self.storage.inspect_upload(self.ref(file))
        except ObjectNotFoundError:
            return None

    async def finish(self, actor, role, file, info):
        if (
            info.size_bytes != file.declared_size_bytes
            or info.checksum_sha256 != f"{file.expected_checksum_sha256}-{file.multipart_count}"
            or info.content_type != "application/octet-stream"
        ):
            raise HTTPException(409, "Multipart object does not match its declaration")
        file.status, file.multipart_state = "uploaded", "completed"
        file.size_bytes, file.checksum_sha256 = info.size_bytes, file.expected_checksum_sha256
        file.content_type, file.storage_etag, file.completed_at = (
            info.content_type,
            info.etag,
            datetime.now(UTC),
        )
        await self.db.commit()
        await self.db.refresh(file)
        return self.files.read(actor, role, file)

    async def complete(self, actor, file_id, ip=""):
        await self.limit(actor, ip, "multipart-complete")
        file, role = await self.own(actor, file_id)
        if file.status == "uploaded":
            return self.files.read(actor, role, file)
        self.active(file, grace=True)
        try:
            info = await self.existing_object(file)
            if info is not None:
                return await self.finish(actor, role, file, info)
            declared = await self.parts(file)
            actual = await self.storage.list_parts(self.ref(file), file.multipart_upload_id)
            if len(actual) != file.multipart_count or len(declared) != file.multipart_count:
                raise HTTPException(409, "Upload every declared part before completing")
            for declaration, part in zip(declared, actual, strict=True):
                self.check_part(declaration, part)
                declaration.storage_etag, declaration.confirmed_at = part.etag, datetime.now(UTC)
            try:
                await self.storage.complete_multipart(
                    self.ref(file), file.multipart_upload_id, actual
                )
            except StorageError:
                info = await self.existing_object(file)
                if info is None:
                    raise
                return await self.finish(actor, role, file, info)
            info = await self.existing_object(file)
            if info is None:
                raise HTTPException(
                    409, "Multipart completion is not yet verified; retry completion"
                )
            return await self.finish(actor, role, file, info)
        except ObjectNotFoundError:
            raise HTTPException(409, "Multipart upload is missing; retry or cancel") from None
        except StorageError:
            raise HTTPException(
                503, "Multipart completion unavailable; retry to reconcile"
            ) from None

    async def abort(self, actor, file_id, ip=""):
        await self.limit(actor, ip, "multipart-abort")
        file, role = await self.own(actor, file_id)
        if file.multipart_state == "aborted":
            return self.files.read(actor, role, file)
        if file.status == "uploaded":
            raise HTTPException(409, "Completed files cannot be cancelled")
        try:
            if await self.existing_object(file) is not None:
                raise HTTPException(409, "Object already exists; retry completion instead")
            await self.storage.abort_multipart(self.ref(file), file.multipart_upload_id)
        except StorageError:
            raise HTTPException(503, "Cancellation unavailable; retry to reconcile") from None
        file.multipart_state = "aborted"
        await self.db.commit()
        await self.db.refresh(file)
        return self.files.read(actor, role, file)
