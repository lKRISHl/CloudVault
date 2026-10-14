"""Opt-in actual S3 contract checks; each fixture owns a unique disposable bucket."""

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from app.core.config import Settings
from app.storage.base import (
    ObjectConflictError,
    ObjectNotFoundError,
    ObjectRef,
    StorageUnavailableError,
)
from app.storage.s3 import S3ObjectStorage

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_S3_ENDPOINT"), reason="Set TEST_S3_ENDPOINT for real storage tests"
)


@pytest_asyncio.fixture
async def storage():
    config = Settings(
        _env_file=None,
        S3_ENDPOINT=os.environ["TEST_S3_ENDPOINT"],
        S3_ACCESS_KEY=os.environ["TEST_S3_ACCESS_KEY"],
        S3_SECRET_KEY=os.environ["TEST_S3_SECRET_KEY"],
        S3_BUCKET_NAME="cv-storage-test-" + uuid4().hex,
    )
    store = S3ObjectStorage(config, uuid4())
    # Creating and deleting this uniquely named bucket never touches the app bucket.
    await asyncio.to_thread(store.client.create_bucket, Bucket=store.bucket)
    try:
        yield store
    finally:
        try:
            pending = await asyncio.to_thread(
                store.client.list_multipart_uploads, Bucket=store.bucket
            )
            for upload in pending.get("Uploads", []):
                await asyncio.to_thread(
                    store.client.abort_multipart_upload,
                    Bucket=store.bucket,
                    Key=upload["Key"],
                    UploadId=upload["UploadId"],
                )
            result = await asyncio.to_thread(store.client.list_objects_v2, Bucket=store.bucket)
            for item in result.get("Contents", []):
                await asyncio.to_thread(
                    store.client.delete_object, Bucket=store.bucket, Key=item["Key"]
                )
            await asyncio.to_thread(store.client.delete_bucket, Bucket=store.bucket)
        finally:
            await store.close()


@pytest.mark.asyncio
async def test_actual_binary_empty_objects_private_bucket_and_delete(storage):
    ref = ObjectRef(storage.tenant_id, uuid4(), uuid4())
    await storage.check_bucket()
    await storage.put_small(ref, b"binary\x00\xff")
    info = await storage.head(ref)
    assert info.size_bytes == 8 and info.content_type == "application/octet-stream"
    assert await storage.read_small(ref) == b"binary\x00\xff"
    with pytest.raises(ValueError, match="read limit"):
        await storage.read_small(ref, 3)
    with pytest.raises(ObjectConflictError):
        await storage.put_small(ref, b"replacement")
    assert await storage.read_small(ref) == b"binary\x00\xff"
    endpoint = os.environ["TEST_S3_ENDPOINT"].rstrip("/")
    async with httpx.AsyncClient() as client:
        assert (await client.get(f"{endpoint}/{storage.bucket}/{ref.key}")).status_code == 403
        assert (await client.get(f"{endpoint}/{storage.bucket}?list-type=2")).status_code == 403
    await storage.delete(ref)
    await storage.delete(ref)  # Idempotent absent-object deletion.
    with pytest.raises(ObjectNotFoundError):
        await storage.head(ref)
    empty = ObjectRef(storage.tenant_id, uuid4(), uuid4())
    await storage.put_small(empty, b"")
    assert await storage.read_small(empty) == b""


@pytest.mark.asyncio
async def test_actual_concurrent_creation_has_one_winner(storage):
    ref = ObjectRef(storage.tenant_id, uuid4(), uuid4())

    async def create():
        try:
            await storage.put_small(ref, b"stable")
            return "created"
        except ObjectConflictError:
            return "conflict"

    assert sorted(await asyncio.gather(create(), create())) == ["conflict", "created"]
    assert await storage.read_small(ref) == b"stable"


@pytest.mark.asyncio
async def test_actual_missing_bucket_and_invalid_credentials_fail_closed(storage):
    missing = S3ObjectStorage(
        Settings(
            _env_file=None,
            S3_ENDPOINT=os.environ["TEST_S3_ENDPOINT"],
            S3_ACCESS_KEY=os.environ["TEST_S3_ACCESS_KEY"],
            S3_SECRET_KEY=os.environ["TEST_S3_SECRET_KEY"],
            S3_BUCKET_NAME="cv-missing-" + uuid4().hex,
        ),
        storage.tenant_id,
    )
    invalid = S3ObjectStorage(
        Settings(
            _env_file=None,
            S3_ENDPOINT=os.environ["TEST_S3_ENDPOINT"],
            S3_ACCESS_KEY="invalid-access",
            S3_SECRET_KEY="invalid-secret",
            S3_BUCKET_NAME=storage.bucket,
        ),
        storage.tenant_id,
    )
    try:
        for store in (missing, invalid):
            with pytest.raises(StorageUnavailableError):
                await store.check_bucket()
    finally:
        await missing.close()
        await invalid.close()
