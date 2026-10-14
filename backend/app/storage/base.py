from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

MAX_INTERNAL_BYTES = 1024 * 1024


class StorageError(Exception):
    """Safe provider-independent error; never expose raw SDK errors to callers."""


class ObjectNotFoundError(StorageError):
    pass


class MultipartNotFoundError(ObjectNotFoundError):
    pass


class ObjectConflictError(StorageError):
    pass


class StorageUnavailableError(StorageError):
    pass


@dataclass(frozen=True)
class ObjectRef:
    tenant_id: UUID
    file_id: UUID
    object_id: UUID

    def __post_init__(self):
        if any(
            not isinstance(value, UUID)
            for value in (
                self.tenant_id,
                self.file_id,
                self.object_id,
            )
        ):
            raise ValueError("Object references require UUID identities")

    @property
    def key(self) -> str:
        return f"tenants/{self.tenant_id}/files/{self.file_id}/objects/{self.object_id}"


@dataclass(frozen=True)
class ObjectInfo:
    size_bytes: int
    content_type: str
    etag: str
    last_modified: datetime
    checksum_sha256: str | None = None


@dataclass(frozen=True)
class UploadGrant:
    url: str
    headers: dict[str, str]


@dataclass(frozen=True)
class StoredPart:
    number: int
    size_bytes: int
    etag: str
    checksum_sha256: str | None


class ObjectStorage(Protocol):
    async def check_bucket(self) -> None: ...
    async def put_small(self, ref: ObjectRef, content: bytes) -> None: ...
    async def head(self, ref: ObjectRef) -> ObjectInfo: ...
    async def read_small(self, ref: ObjectRef, max_bytes: int = MAX_INTERNAL_BYTES) -> bytes: ...
    async def delete(self, ref: ObjectRef) -> None: ...
    async def close(self) -> None: ...
    async def presign_upload(
        self, ref: ObjectRef, size_bytes: int, checksum_sha256: str, expires_seconds: int
    ) -> UploadGrant: ...
    async def inspect_upload(self, ref: ObjectRef) -> ObjectInfo: ...
    async def presign_download(
        self, ref: ObjectRef, filename: str, expires_seconds: int
    ) -> str: ...

    async def create_multipart(self, ref: ObjectRef) -> str: ...
    async def presign_part(
        self,
        ref: ObjectRef,
        upload_id: str,
        number: int,
        size_bytes: int,
        checksum_sha256: str,
        expires_seconds: int,
    ) -> UploadGrant: ...
    async def inspect_part(self, ref: ObjectRef, upload_id: str, number: int) -> StoredPart: ...
    async def list_parts(self, ref: ObjectRef, upload_id: str) -> list[StoredPart]: ...
    async def complete_multipart(
        self, ref: ObjectRef, upload_id: str, parts: list[StoredPart]
    ) -> None: ...
    async def abort_multipart(self, ref: ObjectRef, upload_id: str) -> None: ...
    async def pending_for_object(self, ref: ObjectRef) -> list[str]: ...
