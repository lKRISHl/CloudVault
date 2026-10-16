"""Disposable-provider preview checks; native-container isolation is a separate smoke gate."""

import base64
import hashlib
import os

import httpx
import pytest

from app.core.config import settings
from app.previews.worker import render
from app.schemas.previews import PreviewContent
from tests.api.test_auth import register_user
from tests.api.test_organizations import bearer
from tests.api.test_previews import preview
from tests.test_preview_renderer import image_bytes
from tests.test_uploads_integration import bind, declare, storage

__all__ = ["storage"]
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_S3_ENDPOINT"), reason="Real previews need disposable TEST_S3 storage"
)


@pytest.mark.asyncio
async def test_real_native_history_and_composite_sources_are_verified(client, storage, monkeypatch):
    owner = await register_user(client)
    await bind(storage, owner, monkeypatch)

    async def fixture_renderer(data, page):
        return PreviewContent.model_validate(render(data, page))

    monkeypatch.setattr("app.services.previews.isolated_render", fixture_renderer)
    part_size = 5 * 1024 * 1024
    monkeypatch.setattr(settings, "MULTIPART_PART_BYTES", part_size)
    original = image_bytes()
    async with httpx.AsyncClient(timeout=30) as transfer:
        response = await client.post(
            "/api/v1/files/uploads", headers=bearer(owner), json=declare(original)
        )
        assert response.status_code == 201, response.text
        ticket = response.json()
        assert (await transfer.put(
            ticket["upload_url"], headers=ticket["headers"], content=original
        )).status_code == 200
        fid = ticket["file"]["id"]
        assert (await client.post(
            f"/api/v1/files/{fid}/complete", headers=bearer(owner)
        )).status_code == 200
        response = await preview(client, owner, fid)
        assert response.status_code == 200 and response.json()["kind"] == "image"
        original_id = response.json()["version_id"]
        root = f"/api/v1/files/{fid}/versions"
        pieces = [b"v" * part_size, b"final verified text"]
        hashes = [base64.b64encode(hashlib.sha256(part).digest()).decode() for part in pieces]
        composite = base64.b64encode(hashlib.sha256(
            b"".join(base64.b64decode(value) for value in hashes)
        ).digest()).decode()
        declaration = declare(b"unused")
        declaration.pop("name")
        response = await client.post(root + "/multipart", headers=bearer(owner), json={
            **declaration, "base_generation": 1, "part_size": part_size,
            "declared_size_bytes": sum(map(len, pieces)),
            "checksum_sha256": composite, "checksums": hashes,
        })
        assert response.status_code == 201, response.text
        vid = response.json()["version"]["id"]
        assert (await preview(client, owner, fid, version_id=vid)).status_code == 409
        for number, piece in enumerate(pieces, 1):
            response = await client.post(root + f"/{vid}/parts/{number}/url", headers=bearer(owner))
            assert response.status_code == 200, response.text
            grant = response.json()
            assert (await transfer.put(
                grant["upload_url"], headers=grant["headers"], content=piece
            )).status_code == 200
            assert (await client.post(
                root + f"/{vid}/parts/{number}/confirm", headers=bearer(owner)
            )).status_code == 200
        assert (await client.post(
            root + f"/{vid}/complete", headers=bearer(owner)
        )).status_code == 200
        response = await preview(client, owner, fid)
        assert response.status_code == 200, response.text
        assert response.json()["kind"] == "text" and response.json()["truncated"]
        assert response.json()["text"] == "v" * 65536
        response = await preview(client, owner, fid, version_id=original_id)
        assert response.status_code == 200 and response.json()["kind"] == "image"
