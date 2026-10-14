import asyncio
import re
import unicodedata
from contextlib import suppress
from urllib.parse import quote
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.storage.base import (
    MAX_INTERNAL_BYTES,
    MultipartNotFoundError,
    ObjectConflictError,
    ObjectInfo,
    ObjectNotFoundError,
    ObjectRef,
    StorageUnavailableError,
    StoredPart,
    UploadGrant,
)


class S3ObjectStorage:
    """Tenant-scoped S3 adapter. Large user transfers belong on presigned URLs."""

    def __init__(self, config: Settings, tenant_id: UUID):
        if not isinstance(tenant_id, UUID):
            raise ValueError("Storage scope requires a tenant UUID")
        if not config.S3_BUCKET_NAME:
            raise ValueError("Object storage is not configured")
        self.tenant_id = tenant_id
        self.bucket = config.S3_BUCKET_NAME
        self.config = config
        self.client = self._client(config.S3_ENDPOINT)
        self.signer = (
            self._client(config.S3_PUBLIC_ENDPOINT) if config.S3_PUBLIC_ENDPOINT else self.client
        )

    def _client(self, endpoint):
        config = self.config
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=config.S3_REGION,
            aws_access_key_id=config.S3_ACCESS_KEY.get_secret_value()
            if config.S3_ACCESS_KEY
            else None,
            aws_secret_access_key=config.S3_SECRET_KEY.get_secret_value()
            if config.S3_SECRET_KEY
            else None,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": config.S3_ADDRESSING_STYLE},
                connect_timeout=config.S3_CONNECT_TIMEOUT_SECONDS,
                read_timeout=config.S3_READ_TIMEOUT_SECONDS,
                retries={"mode": "standard", "total_max_attempts": 2},
            ),
        )

    def key(self, ref: ObjectRef) -> str:
        if not isinstance(ref, ObjectRef) or ref.tenant_id != self.tenant_id:
            raise ValueError("Object reference does not belong to the storage tenant")
        return ref.key

    async def call(self, operation, **kwargs):
        return await asyncio.to_thread(self._call, operation, **kwargs)

    def _call(self, operation, **kwargs):
        try:
            return operation(Bucket=self.bucket, **kwargs)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code == "NoSuchUpload":
                raise MultipartNotFoundError("Multipart upload not found") from None
            if code in ("NoSuchKey", "404", "NotFound") and operation == self.client.head_object:
                raise ObjectNotFoundError("Object not found") from None
            if code == "NoSuchKey":
                raise ObjectNotFoundError("Object not found") from None
            if code in ("PreconditionFailed", "ConditionalRequestConflict", "412", "409"):
                raise ObjectConflictError("Object already exists or changed concurrently") from None
            raise StorageUnavailableError("Object storage operation failed") from None
        except BotoCoreError:
            raise StorageUnavailableError("Object storage operation failed") from None

    async def check_bucket(self) -> None:
        await self.call(self.client.head_bucket)

    async def put_small(self, ref: ObjectRef, content: bytes) -> None:
        key = self.key(ref)
        if not isinstance(content, bytes) or len(content) > MAX_INTERNAL_BYTES:
            raise ValueError("Internal object writes require bytes up to 1 MiB")
        await self.call(
            self.client.put_object,
            Key=key,
            Body=content,
            ContentType="application/octet-stream",
            IfNoneMatch="*",
        )

    async def head(self, ref: ObjectRef) -> ObjectInfo:
        result = await self.call(self.client.head_object, Key=self.key(ref))
        return ObjectInfo(
            size_bytes=result["ContentLength"],
            content_type=result.get("ContentType", "application/octet-stream"),
            etag=result["ETag"],
            last_modified=result["LastModified"],
        )

    async def read_small(self, ref: ObjectRef, max_bytes: int = MAX_INTERNAL_BYTES) -> bytes:
        key = self.key(ref)
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_INTERNAL_BYTES:
            raise ValueError("Internal object reads require a limit from 1 byte to 1 MiB")
        info = await self.head(ref)
        if info.size_bytes > max_bytes:
            raise ValueError("Object exceeds the internal read limit")
        if info.size_bytes == 0:
            return b""

        # Request at most limit + 1, so a large object cannot consume unbounded memory.
        def consume():
            # Open, consume and close on the same worker even if the awaiting task is cancelled.
            result = self._call(
                self.client.get_object, Key=key, Range=f"bytes=0-{max_bytes}", IfMatch=info.etag
            )
            stream = result["Body"]
            try:
                content = stream.read(max_bytes + 1)
                if len(content) > max_bytes:
                    raise ValueError("Object exceeds the internal read limit")
                if len(content) != info.size_bytes:
                    raise StorageUnavailableError("Object storage read failed")
                return content
            finally:
                stream.close()

        try:
            return await asyncio.to_thread(consume)
        except (BotoCoreError, OSError):
            raise StorageUnavailableError("Object storage read failed") from None

    async def delete(self, ref: ObjectRef) -> None:
        await self.call(self.client.delete_object, Key=self.key(ref))

    async def close(self) -> None:
        if self.signer is not self.client:
            await asyncio.to_thread(self.signer.close)
        await asyncio.to_thread(self.client.close)

    async def presign_upload(
        self, ref: ObjectRef, size_bytes: int, checksum_sha256: str, expires_seconds: int
    ) -> UploadGrant:
        key = self.key(ref)
        if not 1 <= expires_seconds <= 1800:
            raise ValueError("Invalid upload URL lifetime")
        try:
            url = await asyncio.to_thread(
                self.signer.generate_presigned_url,
                "put_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ContentLength": size_bytes,
                    "ChecksumSHA256": checksum_sha256,
                    "ContentType": "application/octet-stream",
                    "IfNoneMatch": "*",
                },
                ExpiresIn=expires_seconds,
                HttpMethod="PUT",
            )
        except BotoCoreError:
            raise StorageUnavailableError("Cannot authorize upload") from None
        return UploadGrant(
            url=url,
            headers={
                "Content-Type": "application/octet-stream",
                "x-amz-checksum-sha256": checksum_sha256,
                "If-None-Match": "*",
            },
        )

    async def inspect_upload(self, ref: ObjectRef) -> ObjectInfo:
        result = await self.call(self.client.head_object, Key=self.key(ref), ChecksumMode="ENABLED")
        return ObjectInfo(
            size_bytes=result["ContentLength"],
            content_type=result.get("ContentType", "application/octet-stream"),
            etag=result["ETag"],
            last_modified=result["LastModified"],
            checksum_sha256=result.get("ChecksumSHA256"),
        )

    async def presign_download(self, ref: ObjectRef, filename: str, expires_seconds: int) -> str:
        key = self.key(ref)
        if not 1 <= expires_seconds <= 900:
            raise ValueError("Invalid download URL lifetime")
        # Header-safe basename with an ASCII fallback and RFC 5987 Unicode filename.
        name = (
            "".join(
                c if unicodedata.category(c)[0] != "C" and c not in "/\\" else "_" for c in filename
            )[:255]
            or "download"
        )
        fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:200] or "download"
        disposition = (
            f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name, safe='')}"
        )
        try:
            return await asyncio.to_thread(
                self.signer.generate_presigned_url,
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ResponseContentDisposition": disposition,
                    "ResponseContentType": "application/octet-stream",
                    "ResponseCacheControl": "no-store",
                },
                ExpiresIn=expires_seconds,
                HttpMethod="GET",
            )
        except BotoCoreError:
            raise StorageUnavailableError("Cannot authorize download") from None

    async def create_multipart(self, ref: ObjectRef) -> str:
        result = await self.call(
            self.client.create_multipart_upload,
            Key=self.key(ref),
            ContentType="application/octet-stream",
            ChecksumAlgorithm="SHA256",
            ChecksumType="COMPOSITE",
        )
        return result["UploadId"]

    async def presign_part(
        self,
        ref: ObjectRef,
        upload_id: str,
        number: int,
        size_bytes: int,
        checksum_sha256: str,
        expires_seconds: int,
    ) -> UploadGrant:
        key = self.key(ref)
        if (
            not 1 <= number <= 1024
            or not 1 <= size_bytes <= 33554432
            or not 1 <= expires_seconds <= 1800
        ):
            raise ValueError("Invalid multipart grant")
        try:
            url = await asyncio.to_thread(
                self.signer.generate_presigned_url,
                "upload_part",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "UploadId": upload_id,
                    "PartNumber": number,
                    "ContentLength": size_bytes,
                    "ChecksumSHA256": checksum_sha256,
                },
                ExpiresIn=expires_seconds,
                HttpMethod="PUT",
            )
        except BotoCoreError:
            raise StorageUnavailableError("Cannot authorize upload part") from None
        return UploadGrant(url, {"x-amz-checksum-sha256": checksum_sha256})

    @staticmethod
    def stored_part(part) -> StoredPart:
        return StoredPart(
            part["PartNumber"], part["Size"], part["ETag"], part.get("ChecksumSHA256")
        )

    async def inspect_part(self, ref: ObjectRef, upload_id: str, number: int) -> StoredPart:
        if not 1 <= number <= 1024:
            raise ValueError("Invalid part number")
        result = await self.call(
            self.client.list_parts,
            Key=self.key(ref),
            UploadId=upload_id,
            PartNumberMarker=number - 1,
            MaxParts=1,
        )
        parts = result.get("Parts", [])
        if not parts or parts[0]["PartNumber"] != number:
            raise ObjectNotFoundError("Upload part not found")
        return self.stored_part(parts[0])

    async def list_parts(self, ref: ObjectRef, upload_id: str) -> list[StoredPart]:
        key, marker, parts = self.key(ref), 0, []
        while True:
            result = await self.call(
                self.client.list_parts,
                Key=key,
                UploadId=upload_id,
                PartNumberMarker=marker,
                MaxParts=1000,
            )
            parts.extend(self.stored_part(part) for part in result.get("Parts", []))
            if len(parts) > 1024:
                raise StorageUnavailableError("Unexpected multipart manifest")
            if not result.get("IsTruncated"):
                return parts
            next_marker = result.get("NextPartNumberMarker", 0)
            if next_marker <= marker:
                raise StorageUnavailableError("Invalid multipart pagination")
            marker = next_marker

    async def complete_multipart(
        self, ref: ObjectRef, upload_id: str, parts: list[StoredPart]
    ) -> None:
        if not 1 <= len(parts) <= 1024 or [part.number for part in parts] != list(
            range(1, len(parts) + 1)
        ):
            raise ValueError("Invalid multipart manifest")
        await self.call(
            self.client.complete_multipart_upload,
            Key=self.key(ref),
            UploadId=upload_id,
            MultipartUpload={
                "Parts": [
                    {
                        "PartNumber": part.number,
                        "ETag": part.etag,
                        "ChecksumSHA256": part.checksum_sha256,
                    }
                    for part in parts
                ]
            },
            IfNoneMatch="*",
            ChecksumType="COMPOSITE",
        )

    async def abort_multipart(self, ref: ObjectRef, upload_id: str) -> None:
        with suppress(MultipartNotFoundError):
            await self.call(
                self.client.abort_multipart_upload, Key=self.key(ref), UploadId=upload_id
            )
