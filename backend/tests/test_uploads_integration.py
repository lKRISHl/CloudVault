import base64
import hashlib
import os
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.api.storage import get_upload_storage
from app.core.config import settings
from app.main import app
from app.models import File
from app.storage.base import ObjectRef
from tests import test_storage_integration
from tests.api.test_auth import register_user
from tests.api.test_organizations import bearer

storage = test_storage_integration.storage

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_S3_ENDPOINT"), reason="Real S3 upload tests need TEST_S3_ENDPOINT"
)


def declare(body, name="Actual.txt"):
    return {
        "name": name,
        "declared_size_bytes": len(body),
        "declared_content_type": "text/plain",
        "checksum_sha256": base64.b64encode(hashlib.sha256(body).digest()).decode(),
        "request_id": str(uuid4()),
    }


async def bind(store, owner, monkeypatch):
    store.tenant_id = UUID(owner["user"]["tenant"]["id"])
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", store.bucket)

    async def dependency():
        yield store

    app.dependency_overrides[get_upload_storage] = dependency


@pytest.mark.asyncio
async def test_actual_presigned_upload_completion_and_immutable_replay(
    client, db_factory, storage, monkeypatch
):
    owner = await register_user(client)
    await bind(storage, owner, monkeypatch)
    content = b"Real browser-compatible direct storage upload\x00"
    data = declare(content)
    ticket_response = await client.post("/api/v1/files/uploads", headers=bearer(owner), json=data)
    assert ticket_response.status_code == 201
    ticket = ticket_response.json()
    endpoint = f"/api/v1/files/{ticket['file']['id']}/complete"
    assert (await client.post(endpoint, headers=bearer(owner))).status_code == 409
    async with httpx.AsyncClient() as transfer:
        result = await transfer.put(
            ticket["upload_url"], headers=ticket["headers"], content=content
        )
        assert result.status_code == 200
        completed = await client.post(endpoint, headers=bearer(owner))
        assert completed.status_code == 200
        download = await client.post(
            f"/api/v1/files/{ticket['file']['id']}/download-url", headers=bearer(owner)
        )
        assert download.status_code == 200, download.text
        received = await transfer.get(download.json()["download_url"])
        assert received.status_code == 200 and received.content == content
        assert received.headers["content-type"] == "application/octet-stream"
        assert received.headers["content-disposition"].startswith("attachment;")
        assert received.headers["cache-control"] == "no-store"
        tampered = download.json()["download_url"].replace(
            "response-cache-control=no-store", "response-cache-control=public"
        )
        assert (await transfer.get(tampered)).status_code == 403
        assert (
            completed.json()["status"] == "uploaded"
            and completed.json()["checksum_sha256"] == data["checksum_sha256"]
        )
        assert (
            await transfer.put(ticket["upload_url"], headers=ticket["headers"], content=content)
        ).status_code == 412
        assert (await client.post(endpoint, headers=bearer(owner))).json()[
            "completed_at"
        ] == completed.json()["completed_at"]
    async with db_factory() as db:
        file = await db.get(File, UUID(ticket["file"]["id"]))
        assert file.storage_bucket == storage.bucket and file.size_bytes == len(content)
        assert (
            await storage.read_small(ObjectRef(file.tenant_id, file.id, file.object_id)) == content
        )


@pytest.mark.asyncio
async def test_actual_signed_size_checksum_and_provider_metadata_rejection(
    client, db_factory, storage, monkeypatch
):
    owner = await register_user(client)
    await bind(storage, owner, monkeypatch)
    body = b"original"
    data = declare(body)
    ticket = (await client.post("/api/v1/files/uploads", headers=bearer(owner), json=data)).json()
    async with httpx.AsyncClient() as transfer:
        assert (
            await transfer.put(ticket["upload_url"], headers=ticket["headers"], content=b"modified")
        ).status_code == 400
        assert (
            await transfer.put(
                ticket["upload_url"], headers=ticket["headers"], content=b"wrong length"
            )
        ).status_code in (400, 403)
        altered = {**ticket["headers"], "Content-Type": "text/html"}
        assert (
            await transfer.put(ticket["upload_url"], headers=altered, content=body)
        ).status_code == 403
    async with db_factory() as db:
        file = await db.get(File, UUID(ticket["file"]["id"]))
        key = ObjectRef(file.tenant_id, file.id, file.object_id).key
        # Test-only provider admin bypass proves completion does not trust DB declarations.
        await storage.call(
            storage.client.put_object,
            Key=key,
            Body=b"wrong",
            ContentType="application/octet-stream",
        )
    response = await client.post(
        f"/api/v1/files/{ticket['file']['id']}/complete", headers=bearer(owner)
    )
    assert response.status_code == 409
    async with db_factory() as db:
        file = await db.scalar(select(File))
        assert file.status == "pending" and file.size_bytes is None
