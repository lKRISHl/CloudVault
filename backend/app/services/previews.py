import asyncio
import base64
import hashlib
import json
import struct
import unicodedata
from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models import FileVersion
from app.schemas.previews import PreviewContent, PreviewRead
from app.services.accounts import AccountService
from app.services.versions import VersionService
from app.storage.base import ObjectNotFoundError, ObjectRef, StorageError

MAX_SOURCE = 10 * 1024 * 1024
MAX_OUTPUT = 1500 * 1024
READ_GATE = asyncio.Semaphore(2)


def native_type(data):
    if data[4:8] == b"ftyp":
        return "video/mp4"
    if data.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    for signature, detected in [
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
    ]:
        if data.startswith(signature):
            return detected
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def text_or_unsupported(data):
    if data[4:8] == b"ftyp" or data.startswith(b"\x1aE\xdf\xa3"):
        return PreviewContent(
            kind="unsupported", reason="Video preview is not available; download the original"
        )
    try:
        text = data.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        return PreviewContent(kind="unsupported", reason="Unsupported or binary content")
    if any(unicodedata.category(c) in ("Cc", "Cs") and c not in "\n\r\t" for c in text):
        return PreviewContent(kind="unsupported", reason="Binary or unsafe control characters")
    shortened = text[:65536]
    # Expose bidi/format controls rather than allowing visual text spoofing.
    shortened = "".join(
        f"\\u{ord(c):04x}" if unicodedata.category(c) == "Cf" else c for c in shortened
    )
    return PreviewContent(
        kind="text",
        detected_type="text/plain; charset=utf-8",
        text=shortened[:262144],
        truncated=len(text) > 65536 or len(shortened) > 262144,
    )


async def isolated_render(data, page):
    writer = None
    try:
        async with asyncio.timeout(15):
            reader, writer = await asyncio.open_unix_connection(settings.PREVIEW_SOCKET)
            writer.write(struct.pack("!II", len(data), page) + data)
            await writer.drain()
            size = struct.unpack("!I", await reader.readexactly(4))[0]
            if size > MAX_OUTPUT:
                raise ValueError("output_limit")
            result = PreviewContent.model_validate(json.loads(await reader.readexactly(size)))
            if (
                result.kind == "unsupported"
                and result.reason == "Renderer busy or resource limit reached"
            ):
                raise ValueError("renderer_busy")
            if result.kind not in ("image", "pdf", "video", "unsupported"):
                raise ValueError("unexpected_kind")
            if result.kind != "unsupported":
                png = base64.b64decode(result.image_base64 or "", validate=True)
                if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > 1024 * 1024:
                    raise ValueError("invalid_image")
                if result.page != page or result.detected_type != native_type(data):
                    raise ValueError("invalid_identity")
            return result
    except (
        OSError,
        ValueError,
        TimeoutError,
        asyncio.IncompleteReadError,
        AttributeError,
        NotImplementedError,
    ):
        raise HTTPException(503, "Isolated preview renderer unavailable; retry later") from None
    finally:
        if writer:
            writer.close()


class PreviewService:
    def __init__(self, db, storage, renderer=None):
        self.db, self.storage, self.renderer = db, storage, renderer or isolated_render
        self.versions = VersionService(db)

    async def create(self, actor, file_id: UUID, payload, ip):
        actor = SimpleNamespace(id=actor.id, tenant_id=actor.tenant_id)
        await AccountService(self.db).limit(
            "file-preview", ip, str(actor.id), max_identity=100, max_ip=500
        )
        file, _ = await self.versions.access(actor, file_id)
        generation = file.version_generation
        version_id = payload.version_id or await self.db.scalar(
            select(FileVersion.id).where(
                FileVersion.file_id == file.id,
                FileVersion.tenant_id == actor.tenant_id,
                FileVersion.number == file.current_version,
            )
        )
        version = await self.versions.find(actor, file, version_id)
        if version.status != "uploaded":
            raise HTTPException(409, "Only completed retained versions can be previewed")
        if version.storage_bucket != settings.S3_BUCKET_NAME:
            raise HTTPException(503, "Preview storage configuration changed")
        if READ_GATE.locked():
            raise HTTPException(
                503, "Preview capacity busy; retry later", headers={"Retry-After": "2"}
            )
        if version.size_bytes > MAX_SOURCE:
            result = PreviewContent(
                kind="unsupported", reason="Preview source limit is 10 MiB; download the original"
            )
        else:
            async with READ_GATE:
                ref = ObjectRef(file.tenant_id, file.id, version.object_id)
                expected = version.checksum_sha256
                kind, part_size, count, size, etag = (
                    version.checksum_kind,
                    version.multipart_part_size,
                    version.multipart_count,
                    version.size_bytes,
                    version.storage_etag,
                )
                try:
                    info = await self.storage.inspect_upload(ref)
                    if (
                        info.size_bytes != size
                        or info.etag != etag
                        or info.content_type != "application/octet-stream"
                        or info.checksum_sha256
                        != (f"{expected}-{count}" if kind == "sha256-composite" else expected)
                    ):
                        raise HTTPException(409, "Stored content no longer matches verification")
                    data = await self.storage.read_for_processing(ref, MAX_SOURCE)
                except ObjectNotFoundError:
                    raise HTTPException(409, "Preview source unavailable") from None
                except (StorageError, ValueError):
                    raise HTTPException(503, "Preview source read unavailable") from None
                if kind == "sha256-composite":
                    hashes = b"".join(
                        hashlib.sha256(data[n : n + part_size]).digest()
                        for n in range(0, len(data), part_size)
                    )
                    digest = hashlib.sha256(hashes).digest()
                else:
                    digest = hashlib.sha256(data).digest()
                if len(data) != size or base64.b64encode(digest).decode() != expected:
                    raise HTTPException(409, "Preview source checksum changed")
                result = (
                    await self.renderer(data, payload.page)
                    if native_type(data)
                    else text_or_unsupported(data)
                )
        # No durable derivative exists; recheck current ACL/prune/trash before response.
        await self.db.rollback()
        file, _ = await self.versions.access(actor, file_id)
        version = await self.versions.find(actor, file, version_id)
        if payload.version_id is None and file.version_generation != generation:
            raise HTTPException(409, "Current version changed; refresh preview")
        return PreviewRead(
            **result.model_dump(),
            file_id=file.id,
            version_id=version.id,
            version_number=version.number,
            name=file.name,
            generation=file.version_generation,
        )
