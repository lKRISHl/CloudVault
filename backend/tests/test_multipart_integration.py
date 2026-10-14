import base64
import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest

from app.api.storage import get_upload_storage
from app.core.config import settings
from app.jobs import cleanup_uploads
from app.main import app
from app.models import File, UploadIntent
from app.services.upload_cleanup import UploadCleanupService
from app.storage.base import MultipartNotFoundError, ObjectRef, StorageUnavailableError
from tests import test_storage_integration
from tests.api.test_auth import register_user
from tests.api.test_organizations import bearer

storage = test_storage_integration.storage
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_S3_ENDPOINT"), reason="Real multipart tests require disposable S3 settings"
)


@pytest.mark.asyncio
async def test_actual_multipart_parts_integrity_completion_download_and_abort(
    client, storage, monkeypatch
):
    owner = await register_user(client)
    storage.tenant_id = UUID(owner["user"]["tenant"]["id"])
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", storage.bucket)
    monkeypatch.setattr(settings, "MULTIPART_PART_BYTES", 5 * 1024 * 1024)

    async def override():
        yield storage

    app.dependency_overrides[get_upload_storage] = override
    body = b"X" * (5 * 1024 * 1024) + b"last bytes"
    pieces = [body[: 5 * 1024 * 1024], body[5 * 1024 * 1024 :]]
    hashes = [base64.b64encode(hashlib.sha256(part).digest()).decode() for part in pieces]
    request = {
        "name": "Multipart.bin",
        "declared_size_bytes": len(body),
        "declared_content_type": "application/octet-stream",
        "part_size": 5 * 1024 * 1024,
        "checksums": hashes,
        "request_id": str(uuid4()),
    }
    ticket_response = await client.post(
        "/api/v1/files/multipart/uploads", headers=bearer(owner), json=request
    )
    assert ticket_response.status_code == 201, ticket_response.text
    ticket = ticket_response.json()
    id = ticket["file"]["id"]
    async with httpx.AsyncClient(timeout=30) as transfer:
        bad = await transfer.put(
            ticket["parts"][0]["upload_url"],
            headers=ticket["parts"][0]["headers"],
            content=b"wrong",
        )
        assert bad.status_code in [400, 403]
        corrupt = await transfer.put(
            ticket["parts"][0]["upload_url"],
            headers=ticket["parts"][0]["headers"],
            content=b"Z" * len(pieces[0]),
        )
        assert corrupt.status_code == 400
        for part, piece in zip(ticket["parts"], pieces, strict=True):
            sent = await transfer.put(part["upload_url"], headers=part["headers"], content=piece)
            assert sent.status_code == 200, sent.text
            receipt = await client.post(
                f"/api/v1/files/{id}/multipart/parts/{part['number']}/confirm",
                headers=bearer(owner),
            )
            assert receipt.status_code == 200, receipt.text
        completed = await client.post(
            f"/api/v1/files/{id}/multipart/complete", headers=bearer(owner)
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["checksum_kind"] == "sha256-composite" and completed.json()[
            "size_bytes"
        ] == len(body)
        assert completed.json()["multipart_count"] == 2
        assert (
            await client.post(f"/api/v1/files/{id}/multipart/complete", headers=bearer(owner))
        ).json()["completed_at"] == completed.json()["completed_at"]
        download = await client.post(f"/api/v1/files/{id}/download-url", headers=bearer(owner))
        assert download.status_code == 200, download.text
        assert (await transfer.get(download.json()["download_url"])).content == body
        another = await client.post(
            "/api/v1/files/multipart/uploads",
            headers=bearer(owner),
            json={**request, "name": "Cancel.bin", "request_id": str(uuid4())},
        )
        cancelled = another.json()
        cancel_id = cancelled["file"]["id"]
        part = cancelled["parts"][0]
        assert (
            await transfer.put(part["upload_url"], headers=part["headers"], content=pieces[0])
        ).status_code == 200
        assert (
            await client.post(f"/api/v1/files/{cancel_id}/multipart/abort", headers=bearer(owner))
        ).status_code == 200
        assert (
            await transfer.put(part["upload_url"], headers=part["headers"], content=pieces[0])
        ).status_code == 404


@pytest.mark.asyncio
async def test_real_cleanup_reclaims_name_retries_late_bytes_and_aborts_unknown_upload(
    client, db_factory, storage, monkeypatch
):
    owner = await register_user(client)
    tenant_id = UUID(owner["user"]["tenant"]["id"])
    storage.tenant_id = tenant_id
    for field in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        monkeypatch.setattr(settings, field, getattr(storage.config, field))
    monkeypatch.setattr(settings, "S3_PUBLIC_ENDPOINT", None)
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", storage.bucket)

    async def override():
        yield storage

    app.dependency_overrides[get_upload_storage] = override
    body = b"Abandoned basic upload"
    digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
    metadata = {
        "name": "Expired.txt",
        "declared_size_bytes": len(body),
        "checksum_sha256": digest,
        "request_id": str(uuid4()),
    }
    ticket = (
        await client.post("/api/v1/files/uploads", headers=bearer(owner), json=metadata)
    ).json()
    file_id = UUID(ticket["file"]["id"])
    async with httpx.AsyncClient(timeout=30) as transfer:
        assert (
            await transfer.put(ticket["upload_url"], content=body, headers=ticket["headers"])
        ).status_code == 200
        async with db_factory() as db:
            file = await db.get(File, file_id)
            file.upload_expires_at = datetime.now(UTC) - timedelta(hours=2)
            await db.commit()
        await cleanup_uploads.tick(factory=db_factory)
        assert not (await client.get("/api/v1/files", headers=bearer(owner))).json()["items"]
        replacement = await client.post(
            "/api/v1/files/uploads",
            headers=bearer(owner),
            json={**metadata, "request_id": str(uuid4())},
        )
        assert replacement.status_code == 201
        # The provider URL is deliberately still valid in this clock-controlled test:
        # simulate a write that finishes after the cleanup observation.
        assert (
            await transfer.put(ticket["upload_url"], content=body, headers=ticket["headers"])
        ).status_code == 200
        async with db_factory() as db:
            assert await UploadCleanupService(db, storage).sweep(file_id, tenant_id)
        orphan = ObjectRef(tenant_id, uuid4(), uuid4())
        orphan_id = await storage.create_multipart(orphan)
        orphan_body = b"untracked part"
        orphan_hash = base64.b64encode(hashlib.sha256(orphan_body).digest()).decode()
        grant = await storage.presign_part(orphan, orphan_id, 1, len(orphan_body), orphan_hash, 300)
        assert (
            await transfer.put(grant.url, content=orphan_body, headers=grant.headers)
        ).status_code == 200
        inventory = await storage.call(
            storage.client.list_multipart_uploads, Prefix="", MaxUploads=100
        )
        assert any(item["UploadId"] == orphan_id for item in inventory.get("Uploads", [])), {
            key: value for key, value in inventory.items() if key != "ResponseMetadata"
        }
        await cleanup_uploads.sweep_orphans(
            storage, db_factory, now=datetime.now(UTC) + timedelta(days=1)
        )
        with pytest.raises(MultipartNotFoundError):
            await storage.list_parts(orphan, orphan_id)
        original_create = storage.create_multipart
        lost_ids = []

        async def lost_create(ref):
            lost_ids.append((ref, await original_create(ref)))
            raise StorageUnavailableError("lost create acknowledgement")

        monkeypatch.setattr(storage, "create_multipart", lost_create)
        part_size = settings.MULTIPART_PART_BYTES
        initialization = await client.post(
            "/api/v1/files/multipart/uploads",
            headers=bearer(owner),
            json={
                "name": "Lost create.bin",
                "declared_size_bytes": 1,
                "part_size": part_size,
                "checksums": [base64.b64encode(hashlib.sha256(b"x").digest()).decode()],
                "request_id": str(uuid4()),
            },
        )
        assert initialization.status_code == 503
        monkeypatch.setattr(storage, "create_multipart", original_create)
        ref, upload_id = lost_ids[0]
        async with db_factory() as db:
            intent = await db.get(UploadIntent, ref.file_id)
            assert intent.object_id == ref.object_id and await db.get(File, ref.file_id) is None
            intent.expires_at = datetime.now(UTC) - timedelta(hours=2)
            await db.commit()
        await cleanup_uploads.tick(factory=db_factory)
        with pytest.raises(MultipartNotFoundError):
            await storage.list_parts(ref, upload_id)
