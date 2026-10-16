import io
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from app.core.config import Settings
from app.storage.base import (
    MAX_INTERNAL_BYTES,
    MultipartNotFoundError,
    ObjectConflictError,
    ObjectNotFoundError,
    ObjectRef,
    StorageUnavailableError,
    StoredPart,
)
from app.storage.s3 import S3ObjectStorage


def config(**values):
    return Settings(
        _env_file=None,
        S3_BUCKET_NAME="cloudvault-test",
        S3_ENDPOINT="http://localhost:9000",
        S3_ACCESS_KEY="test-access",
        S3_SECRET_KEY="test-secret",
        **values,
    )


@pytest.fixture
def storage():
    store = S3ObjectStorage(config(), uuid4())
    try:
        yield store
    finally:
        store.client.close()


def reference(store):
    return ObjectRef(store.tenant_id, uuid4(), uuid4())


@pytest.mark.parametrize(
    "values",
    [
        {"S3_BUCKET_NAME": None},
        {"S3_BUCKET_NAME": "UpperCase"},
        {"S3_BUCKET_NAME": "192.168.1.1"},
        {"S3_BUCKET_NAME": "bad..bucket"},
        {"S3_SECRET_KEY": None},
        {"S3_ACCESS_KEY": ""},
        {"S3_ENDPOINT": "http://user:password@localhost:9000"},
        {"S3_ENDPOINT": "file:///tmp/storage"},
        {"S3_ENDPOINT": "http://localhost/path"},
        {"S3_ENDPOINT": "https://localhost?secret=bad"},
        {"S3_ADDRESSING_STYLE": "invalid"},
    ],
)
def test_storage_configuration_rejects_unsafe_or_partial_values(values):
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            **{
                "S3_BUCKET_NAME": "cloudvault-test",
                "S3_ENDPOINT": "http://localhost:9000",
                "S3_ACCESS_KEY": "test-access",
                "S3_SECRET_KEY": "test-secret",
                **values,
            },
        )


def test_storage_credentials_are_redacted_and_production_uses_tls():
    settings = config()
    assert "test-secret" not in repr(settings) and "test-access" not in repr(settings)
    assert settings.S3_SECRET_KEY.get_secret_value() == "test-secret"
    for endpoint, secret in (
        ("http://localhost", "secret"),
        ("https://storage.example", "minioadmin"),
    ):
        with pytest.raises(ValueError, match="Production storage"):
            Settings(
                _env_file=None,
                ENVIRONMENT="production",
                SECRET_KEY="x" * 64,
                SMTP_STARTTLS=True,
                FRONTEND_URL="https://app.example",
                S3_ENDPOINT=endpoint,
                S3_BUCKET_NAME="cloudvault-test",
                S3_ACCESS_KEY="access",
                S3_SECRET_KEY=secret,
            )


def test_storage_disabled_and_aws_default_credentials_are_supported():
    disabled = Settings(_env_file=None)
    assert disabled.S3_BUCKET_NAME is None
    with pytest.raises(ValueError, match="not configured"):
        S3ObjectStorage(disabled, uuid4())
    aws = Settings(_env_file=None, S3_BUCKET_NAME="cloudvault-test")
    assert aws.S3_ENDPOINT is None and aws.S3_ACCESS_KEY is None


def test_keys_use_only_uuid_identities_and_reject_foreign_scope(storage):
    ref = reference(storage)
    assert ref.key == f"tenants/{ref.tenant_id}/files/{ref.file_id}/objects/{ref.object_id}"
    assert storage.key(ref) == ref.key
    with pytest.raises(ValueError):
        ObjectRef("../foreign", uuid4(), uuid4())
    with pytest.raises(ValueError):
        storage.key(ObjectRef(uuid4(), ref.file_id, ref.object_id))


@pytest.mark.asyncio
async def test_basic_operations_and_stream_closure(storage):
    ref = reference(storage)
    modified = datetime.now(UTC)
    head = {
        "ContentLength": 4,
        "ETag": '"etag"',
        "ContentType": "application/octet-stream",
        "LastModified": modified,
    }
    stream = StreamingBody(io.BytesIO(b"test"), 4)
    with Stubber(storage.client) as stub:
        stub.add_response("head_bucket", {}, {"Bucket": storage.bucket})
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": storage.bucket,
                "Key": ref.key,
                "Body": b"test",
                "ContentType": "application/octet-stream",
                "IfNoneMatch": "*",
            },
        )
        stub.add_response("head_object", head, {"Bucket": storage.bucket, "Key": ref.key})
        stub.add_response(
            "get_object",
            {"Body": stream},
            {"Bucket": storage.bucket, "Key": ref.key, "Range": "bytes=0-4", "IfMatch": '"etag"'},
        )
        stub.add_response("delete_object", {}, {"Bucket": storage.bucket, "Key": ref.key})
        await storage.check_bucket()
        await storage.put_small(ref, b"test")
        assert await storage.read_small(ref, 4) == b"test"
        assert stream._raw_stream.closed
        await storage.delete(ref)
        stub.assert_no_pending_responses()


@pytest.mark.asyncio
async def test_read_limits_empty_objects_and_oversized_provider_response(storage):
    ref = reference(storage)
    for size in (0, 10):
        with Stubber(storage.client) as stub:
            stub.add_response(
                "head_object",
                {"ContentLength": size, "ETag": '"etag"', "LastModified": datetime.now(UTC)},
                {"Bucket": storage.bucket, "Key": ref.key},
            )
            if size == 0:
                assert await storage.read_small(ref, 4) == b""
            else:
                with pytest.raises(ValueError, match="read limit"):
                    await storage.read_small(ref, 4)
    stream = StreamingBody(io.BytesIO(b"oversize"), 8)
    with Stubber(storage.client) as stub:
        stub.add_response(
            "head_object", {"ContentLength": 4, "ETag": '"etag"', "LastModified": datetime.now(UTC)}
        )
        stub.add_response("get_object", {"Body": stream})
        with pytest.raises(ValueError, match="read limit"):
            await storage.read_small(ref, 4)
        assert stream._raw_stream.closed
    for limit in (0, MAX_INTERNAL_BYTES + 1, True):
        with pytest.raises(ValueError):
            await storage.read_small(ref, limit)
    with pytest.raises(ValueError):
        await storage.put_small(ref, b"x" * (MAX_INTERNAL_BYTES + 1))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,code,status,expected",
    [
        ("head_object", "404", 404, ObjectNotFoundError),
        ("get_object", "NoSuchKey", 404, ObjectNotFoundError),
        ("head_bucket", "404", 404, StorageUnavailableError),
        ("put_object", "PreconditionFailed", 412, ObjectConflictError),
        ("head_object", "AccessDenied", 403, StorageUnavailableError),
        ("head_object", "InternalError", 500, StorageUnavailableError),
    ],
)
async def test_provider_errors_are_classified_without_secret_messages(
    storage, operation, code, status, expected
):
    with Stubber(storage.client) as stub:
        stub.add_client_error(operation, code, "secret-provider-detail", http_status_code=status)
        with pytest.raises(expected) as failure:
            await storage.call(
                getattr(storage.client, operation),
                **({} if operation == "head_bucket" else {"Key": reference(storage).key}),
            )
        assert "secret-provider-detail" not in str(failure.value)


@pytest.mark.asyncio
async def test_connection_failure_and_incomplete_stream_are_safe(storage, monkeypatch):
    def unavailable(**kwargs):
        raise EndpointConnectionError(endpoint_url="secret-endpoint")

    monkeypatch.setattr(storage.client, "head_bucket", unavailable)
    with pytest.raises(StorageUnavailableError) as failure:
        await storage.check_bucket()
    assert "secret-endpoint" not in str(failure.value)
    stream = StreamingBody(io.BytesIO(b"ab"), 4)
    with Stubber(storage.client) as stub:
        stub.add_response(
            "head_object", {"ContentLength": 4, "ETag": '"etag"', "LastModified": datetime.now(UTC)}
        )
        stub.add_response("get_object", {"Body": stream})
        with pytest.raises(StorageUnavailableError, match="read failed"):
            await storage.read_small(reference(storage), 4)
        assert stream._raw_stream.closed


@pytest.mark.asyncio
async def test_every_object_operation_rejects_foreign_scope_before_network(storage):
    foreign = ObjectRef(uuid4(), uuid4(), uuid4())
    with Stubber(storage.client):
        for operation in (storage.head, storage.read_small, storage.delete):
            with pytest.raises(ValueError, match="storage tenant"):
                await operation(foreign)
        with pytest.raises(ValueError, match="storage tenant"):
            await storage.put_small(foreign, b"denied")


@pytest.mark.asyncio
async def test_signed_download_is_scoped_attachment_and_header_safe(storage):
    from urllib.parse import parse_qs, urlsplit

    ref = reference(storage)
    url = await storage.presign_download(ref, 'résumé/"\r\n.html', 300)
    query = parse_qs(urlsplit(url).query)
    disposition = query["response-content-disposition"][0]
    assert disposition.startswith('attachment; filename="')
    assert "filename*=UTF-8''" in disposition and "%C3%A9" in disposition
    assert "\r" not in disposition and "\n" not in disposition
    assert query["response-content-type"] == ["application/octet-stream"]
    assert query["response-cache-control"] == ["no-store"]
    assert query["X-Amz-Expires"] == ["300"]
    assert query["X-Amz-SignedHeaders"] == ["host"]
    with pytest.raises(ValueError):
        await storage.presign_download(ObjectRef(uuid4(), ref.file_id, ref.object_id), "x", 300)
    with pytest.raises(ValueError):
        await storage.presign_download(ref, "x", 901)


@pytest.mark.asyncio
async def test_processing_reads_are_bounded_conditional_and_tenant_scoped(storage):
    from app.storage.base import MAX_PROCESSING_BYTES

    ref = reference(storage)
    body = b"p" * (MAX_INTERNAL_BYTES + 1)
    stream = StreamingBody(io.BytesIO(body), len(body))
    with Stubber(storage.client) as stub:
        stub.add_response(
            "head_object",
            {"ContentLength": len(body), "ETag": '"verified"', "LastModified": datetime.now(UTC)},
        )
        stub.add_response("get_object", {"Body": stream}, {
            "Bucket": storage.bucket, "Key": ref.key,
            "Range": f"bytes=0-{len(body)}", "IfMatch": '"verified"',
        })
        assert await storage.read_for_processing(ref, len(body)) == body
        assert stream._raw_stream.closed
    for maximum in (0, True, MAX_PROCESSING_BYTES + 1):
        with pytest.raises(ValueError):
            await storage.read_for_processing(ref, maximum)
    with pytest.raises(ValueError, match="storage tenant"):
        await storage.read_for_processing(ObjectRef(uuid4(), ref.file_id, ref.object_id), 10)


@pytest.mark.asyncio
async def test_multipart_grants_and_operations_preserve_scope(storage):
    from urllib.parse import parse_qs, urlsplit

    ref = reference(storage)
    grant = await storage.presign_part(ref, "provider-id", 2, 7, "checksum", 300)
    query = parse_qs(urlsplit(grant.url).query)
    assert query["partNumber"] == ["2"] and query["uploadId"] == ["provider-id"]
    assert query["X-Amz-SignedHeaders"] == ["content-length;host;x-amz-checksum-sha256"]
    assert grant.headers == {"x-amz-checksum-sha256": "checksum"}
    for number, size, ttl in [(0, 1, 300), (1025, 1, 300), (1, 33554433, 300), (1, 1, 1801)]:
        with pytest.raises(ValueError):
            await storage.presign_part(ref, "id", number, size, "checksum", ttl)
    foreign = ObjectRef(uuid4(), ref.file_id, ref.object_id)
    with Stubber(storage.client):
        for operation, args in [
            (storage.create_multipart, ()),
            (storage.presign_part, ("id", 1, 1, "checksum", 300)),
            (storage.inspect_part, ("id", 1)),
            (storage.list_parts, ("id",)),
            (storage.pending_for_object, ()),
            (storage.complete_multipart, ("id", [StoredPart(1, 1, "etag", "checksum")])),
            (storage.abort_multipart, ("id",)),
        ]:
            with pytest.raises(ValueError, match="storage tenant"):
                await operation(foreign, *args)


@pytest.mark.asyncio
async def test_multipart_pagination_and_missing_upload_are_safe(storage):
    ref = reference(storage)
    params = {"Bucket": storage.bucket, "Key": ref.key, "UploadId": "id", "MaxParts": 1000}
    with Stubber(storage.client) as stub:
        stub.add_response(
            "list_parts",
            {
                "Parts": [{"PartNumber": 1, "Size": 5, "ETag": "one", "ChecksumSHA256": "hash"}],
                "IsTruncated": True,
                "NextPartNumberMarker": 1,
            },
            {**params, "PartNumberMarker": 0},
        )
        stub.add_response(
            "list_parts",
            {
                "Parts": [{"PartNumber": 2, "Size": 1, "ETag": "two", "ChecksumSHA256": "hash"}],
                "IsTruncated": False,
            },
            {**params, "PartNumberMarker": 1},
        )
        assert [part.number for part in await storage.list_parts(ref, "id")] == [1, 2]
        stub.add_response(
            "list_parts",
            {"IsTruncated": True, "NextPartNumberMarker": 0},
            {**params, "PartNumberMarker": 0},
        )
        with pytest.raises(StorageUnavailableError, match="pagination"):
            await storage.list_parts(ref, "id")
        stub.add_client_error(
            "list_parts", "NoSuchUpload", "secret-provider-id", http_status_code=404
        )
        with pytest.raises(MultipartNotFoundError) as failure:
            await storage.list_parts(ref, "id")
        assert "secret-provider-id" not in str(failure.value)
        stub.add_client_error("abort_multipart_upload", "NoSuchUpload", http_status_code=404)
        await storage.abort_multipart(ref, "id")


@pytest.mark.asyncio
async def test_initialization_inventory_is_exact_key_scoped(storage):
    ref = reference(storage)
    params = {"Bucket": storage.bucket, "Prefix": ref.key, "MaxUploads": 1000}
    with Stubber(storage.client) as stub:
        stub.add_response(
            "list_multipart_uploads",
            {
                "Uploads": [
                    {"Key": ref.key, "UploadId": "owned"},
                    {"Key": ref.key + "-different", "UploadId": "foreign-prefix"},
                ],
                "IsTruncated": False,
            },
            params,
        )
        assert await storage.pending_for_object(ref) == ["owned"]
