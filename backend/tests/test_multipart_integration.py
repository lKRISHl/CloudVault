import base64
import hashlib
import os
from uuid import UUID, uuid4

import httpx
import pytest

from app.api.storage import get_upload_storage
from app.core.config import settings
from app.main import app
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
