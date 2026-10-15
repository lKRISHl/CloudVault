import base64
import hashlib
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models import VersionPart
from app.schemas.versions import VersionMultipartTicket
from app.services.multipart import MultipartService
from app.services.uploads import utc
from app.services.versions import VersionService
from app.storage.base import ObjectNotFoundError, ObjectRef, StorageError


class VersionMultipartService(MultipartService):
    """Use shared part proof/signing primitives with durable version candidates."""

    def __init__(self, db, storage, file_id):
        super().__init__(db, storage)
        self.file_id = file_id
        self.versions = VersionService(db, storage)

    @staticmethod
    def ref(version):
        return ObjectRef(version.tenant_id, version.file_id, version.object_id)

    async def own(self, actor, version_id):
        self.file, role = await self.versions.access(actor, self.file_id, True)
        version = await self.versions.find(actor, self.file, version_id)
        if version.created_by != actor.id:
            raise HTTPException(403, "Only the version uploader can control this transfer")
        if version.upload_method != "multipart":
            raise HTTPException(409, "This version does not use multipart")
        if version.cancelled_at:
            raise HTTPException(410, "Version upload cancelled")
        if version.storage_bucket != settings.S3_BUCKET_NAME:
            raise HTTPException(503, "Version storage configuration changed")
        return version, role

    def active(self, version, grace=False):
        if version.base_generation != self.file.version_generation:
            raise HTTPException(409, "Current version changed; cancel and start again")
        if version.cancelled_at or version.cleaned_at:
            raise HTTPException(410, "Version upload cancelled or cleaned")
        MultipartService.active(version, grace)

    async def parts(self, version):
        return list(
            await self.db.scalars(
                select(VersionPart)
                .where(VersionPart.version_id == version.id)
                .order_by(VersionPart.number)
            )
        )

    async def part(self, version, number):
        part = await self.db.get(VersionPart, (version.id, number))
        if part is None:
            raise HTTPException(404, "Version part not found")
        return part

    async def initialize(self, version):
        if version.multipart_state != "initializing":
            return
        if version.base_generation != self.file.version_generation:
            raise HTTPException(409, "Current version changed; cancel and start again")
        if utc(version.upload_expires_at) <= datetime.now(UTC):
            raise HTTPException(410, "Version upload expired")
        # Exact candidate/key/manifest were committed before any provider create. Retry
        # aborts discoverable unknown ACKs; delayed acknowledgements stay covered by cleanup.
        for upload_id in await self.storage.pending_for_object(self.ref(version)):
            await self.storage.abort_multipart(self.ref(version), upload_id)
        if await self.storage.pending_for_object(self.ref(version)):
            raise StorageError("Previous initialization is not reconciled")
        version.multipart_upload_id = await self.storage.create_multipart(self.ref(version))
        version.multipart_state = "active"
        await self.db.flush()

    async def ticket(self, actor, role, version, grants=True):
        declarations = await self.parts(version)
        parts = []
        for part in declarations:
            if grants and version.status != "uploaded" and not part.confirmed_at:
                self.active(version)
                parts.append(await self.grant(version, part))
            else:
                from app.schemas.multipart import PartTicket

                parts.append(
                    PartTicket(
                        number=part.number,
                        size_bytes=part.size_bytes,
                        checksum_sha256=part.checksum_sha256,
                        confirmed=part.confirmed_at is not None,
                    )
                )
        return VersionMultipartTicket(
            version=self.versions.read(version, self.file, actor),
            part_size=version.multipart_part_size,
            parts=parts,
            expires_at=utc(version.upload_expires_at),
            can_resume=version.status == "pending"
            and not version.cancelled_at
            and version.base_generation == self.file.version_generation
            and datetime.now(UTC) < utc(version.upload_expires_at),
            confirmed_bytes=version.size_bytes
            if version.status == "uploaded"
            else sum(part.size_bytes for part in parts if part.confirmed),
        )

    async def start(self, actor, payload, ip=""):
        size = payload.declared_size_bytes
        count = (size + payload.part_size - 1) // payload.part_size
        if size <= 0 or size > settings.MULTIPART_MAX_BYTES:
            raise HTTPException(413, "Multipart replacement is empty or exceeds limit")
        digest = base64.b64encode(
            hashlib.sha256(
                b"".join(base64.b64decode(value) for value in payload.checksums)
            ).digest()
        ).decode()
        if count != len(payload.checksums) or count > 1024 or digest != payload.checksum_sha256:
            raise HTTPException(422, "Multipart manifest does not match size/checksum")
        self.file, version = await self.versions.reserve(actor, self.file_id, payload, ip, True)
        vid = version.id
        await self.db.commit()  # Durable reference precedes provider-side creation.
        version, role = await self.own(actor, vid)
        try:
            await self.initialize(version)
            result = await self.ticket(actor, role, version)
            await self.db.commit()
            return result
        except StorageError:
            await self.db.rollback()
            raise HTTPException(
                503, "Version initialization unavailable; retry the same request"
            ) from None

    async def finish(self, actor, role, version, info):
        if (
            info.size_bytes != version.declared_size_bytes
            or info.checksum_sha256
            != f"{version.expected_checksum_sha256}-{version.multipart_count}"
            or info.content_type != "application/octet-stream"
            or not info.etag
        ):
            raise HTTPException(409, "Multipart version does not match its declaration")
        version.status, version.multipart_state = "uploaded", "completed"
        version.size_bytes, version.checksum_sha256 = (
            info.size_bytes,
            version.expected_checksum_sha256,
        )
        version.content_type, version.storage_etag, version.completed_at = (
            info.content_type,
            info.etag,
            datetime.now(UTC),
        )
        await self.versions.activate(actor, self.file, version, "upload")
        await self.db.commit()
        await self.db.refresh(self.file)
        return self.files.read(actor, role, self.file)

    async def complete(self, actor, version_id, ip=""):
        await self.limit(actor, ip, "version-complete")
        version, role = await self.own(actor, version_id)
        if version.status == "uploaded":
            return self.files.read(actor, role, self.file)
        self.active(version, grace=True)
        try:
            info = await self.existing_object(version)
            if info is not None:
                return await self.finish(actor, role, version, info)
            declared = await self.parts(version)
            actual = await self.storage.list_parts(self.ref(version), version.multipart_upload_id)
            if len(actual) != version.multipart_count or len(declared) != version.multipart_count:
                raise HTTPException(409, "Upload all declared parts before completion")
            for declaration, part in zip(declared, actual, strict=True):
                self.check_part(declaration, part)
                declaration.storage_etag, declaration.confirmed_at = part.etag, datetime.now(UTC)
            try:
                await self.storage.complete_multipart(
                    self.ref(version), version.multipart_upload_id, actual
                )
            except StorageError:
                if await self.existing_object(version) is None:
                    raise
            info = await self.existing_object(version)
            if info is None:
                raise HTTPException(409, "Completion not verified; retry")
            return await self.finish(actor, role, version, info)
        except ObjectNotFoundError:
            raise HTTPException(
                409, "Multipart version session missing; cancel and start again"
            ) from None
        except StorageError:
            raise HTTPException(
                503, "Multipart completion unavailable; retry to reconcile"
            ) from None

    async def progress(self, actor, version_id, ip=""):
        await self.limit(actor, ip, "version-progress")
        version, role = await self.own(actor, version_id)
        try:
            if version.status != "uploaded" and version.multipart_state != "initializing":
                self.active(version, grace=True)
                info = await self.existing_object(version)
                if info is not None:
                    await self.finish(actor, role, version, info)
                else:
                    await self.reconcile_parts(version)
            result = await self.ticket(actor, role, version, False)
            await self.db.commit()
            return result
        except StorageError:
            raise HTTPException(503, "Progress unavailable; retry") from None

    async def resume(self, actor, version_id, payload, ip=""):
        await self.limit(actor, ip, "version-resume")
        version, role = await self.own(actor, version_id)
        if payload.checksums != [part.checksum_sha256 for part in await self.parts(version)]:
            raise HTTPException(409, "Reselect the original file content")
        try:
            if version.status != "uploaded":
                await self.initialize(version)
                self.active(version)
                info = await self.existing_object(version)
                if info is not None:
                    await self.finish(actor, role, version, info)
                else:
                    await self.reconcile_parts(version)
            result = await self.ticket(actor, role, version)
            await self.db.commit()
            return result
        except StorageError:
            raise HTTPException(503, "Resume unavailable; retry") from None
