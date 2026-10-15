import base64
import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import FileVersion
from app.services.version_cleanup import VersionCleanupService
from app.storage.base import ObjectNotFoundError, ObjectRef
from tests.api.test_auth import register_user
from tests.api.test_organizations import bearer
from tests.test_uploads_integration import bind, declare, storage

__all__ = ["storage"]
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_S3_ENDPOINT"), reason="Real version transfer tests need TEST_S3_ENDPOINT"
)


@pytest.mark.asyncio
async def test_real_version_multipart_resume_restoration_prune_and_cancel_cleanup(
    client, db_factory, storage, monkeypatch
):
    owner = await register_user(client)
    await bind(storage, owner, monkeypatch)
    part_size = 5 * 1024 * 1024
    monkeypatch.setattr(settings, "MULTIPART_PART_BYTES", part_size)
    original = b"Original version survives all candidate failures"
    pieces = [b"v" * part_size, b"verified last part"]
    hashes = [base64.b64encode(hashlib.sha256(piece).digest()).decode() for piece in pieces]
    composite = base64.b64encode(
        hashlib.sha256(b"".join(base64.b64decode(h) for h in hashes)).digest()
    ).decode()
    async with httpx.AsyncClient(timeout=30) as transfer:
        first = (
            await client.post(
                "/api/v1/files/uploads", headers=bearer(owner), json=declare(original)
            )
        ).json()
        assert (
            await transfer.put(first["upload_url"], headers=first["headers"], content=original)
        ).status_code == 200
        fid = first["file"]["id"]
        assert (
            await client.post(f"/api/v1/files/{fid}/complete", headers=bearer(owner))
        ).status_code == 200
        root = f"/api/v1/files/{fid}/versions"
        initial = (await client.get(root, headers=bearer(owner))).json()["items"][0]
        metadata = declare(b"unused")
        metadata.pop("name")
        payload = {
            **metadata,
            "declared_size_bytes": sum(map(len, pieces)),
            "base_generation": 1,
            "checksum_sha256": composite,
            "checksums": hashes,
            "part_size": part_size,
        }
        response = await client.post(root + "/multipart", headers=bearer(owner), json=payload)
        assert response.status_code == 201, response.text
        ticket = response.json()
        vid = ticket["version"]["id"]
        grant = ticket["parts"][0]
        assert (
            await transfer.put(grant["upload_url"], headers=grant["headers"], content=pieces[0])
        ).status_code == 200
        assert (
            await client.post(root + f"/{vid}/parts/1/confirm", headers=bearer(owner))
        ).status_code == 200
        progress = (await client.get(root + f"/{vid}/progress", headers=bearer(owner))).json()
        assert progress["confirmed_bytes"] == part_size and not progress["parts"][0]["upload_url"]
        # Ordinary downloads keep the old current content while a replacement is pending.
        grant = (
            await client.post(f"/api/v1/files/{fid}/download-url", headers=bearer(owner))
        ).json()
        assert (await transfer.get(grant["download_url"])).content == original
        resumed = (
            await client.post(
                root + f"/{vid}/resume", headers=bearer(owner), json={"checksums": hashes}
            )
        ).json()
        assert resumed["parts"][0]["confirmed"] and not resumed["parts"][0]["upload_url"]
        grant = resumed["parts"][1]
        assert (
            await transfer.put(grant["upload_url"], headers=grant["headers"], content=pieces[1])
        ).status_code == 200
        complete = await client.post(root + f"/{vid}/complete", headers=bearer(owner))
        assert complete.status_code == 200, complete.text
        assert complete.json()["checksum_kind"] == "sha256-composite"
        grant = (
            await client.post(f"/api/v1/files/{fid}/download-url", headers=bearer(owner))
        ).json()
        assert (await transfer.get(grant["download_url"])).content == b"".join(pieces)
        assert (
            await client.post(
                root + f"/{initial['id']}/restore",
                headers=bearer(owner),
                json={"base_generation": 2},
            )
        ).status_code == 200
        assert (
            await client.post(
                root + f"/{vid}/prune", headers=bearer(owner), json={"confirmation": "DELETE"}
            )
        ).status_code == 202
        assert (
            await client.post(
                root + f"/{vid}/restore", headers=bearer(owner), json={"base_generation": 3}
            )
        ).status_code == 404
        payload["request_id"] = declare(b"unused")["request_id"]
        payload["base_generation"] = 3
        pending = (
            await client.post(root + "/multipart", headers=bearer(owner), json=payload)
        ).json()
        pid = pending["version"]["id"]
        grant = pending["parts"][0]
        assert (
            await transfer.put(grant["upload_url"], headers=grant["headers"], content=pieces[0])
        ).status_code == 200
        assert (
            await client.post(root + f"/{pid}/cancel", headers=bearer(owner))
        ).status_code == 202
        assert (
            await client.post(root + f"/{pid}/complete", headers=bearer(owner))
        ).status_code == 410
    async with db_factory() as db:
        versions = list(
            await db.scalars(select(FileVersion).where(FileVersion.file_id == UUID(fid)))
        )
        refs = {v.id: ObjectRef(v.tenant_id, v.file_id, v.object_id) for v in versions}
        tenant = versions[0].tenant_id
        await db.rollback()
        later = datetime.now(UTC) + timedelta(days=2)
        assert await VersionCleanupService(db, storage).sweep(UUID(vid), tenant, later)
        assert await VersionCleanupService(db, storage).sweep(UUID(pid), tenant, later)
        for removed in [UUID(vid), UUID(pid)]:
            with pytest.raises(ObjectNotFoundError):
                await storage.inspect_upload(refs[removed])
        assert await storage.read_small(refs[UUID(initial["id"])]) == original
    result = (await client.get(root, headers=bearer(owner))).json()
    assert result["retained_bytes"] == len(original) and result["pending_bytes"] == 0


@pytest.mark.asyncio
async def test_real_empty_replacement_uses_basic_and_downloads_zero_bytes(
    client, storage, monkeypatch
):
    owner = await register_user(client)
    await bind(storage, owner, monkeypatch)
    async with httpx.AsyncClient(timeout=30) as transfer:
        first = (
            await client.post(
                "/api/v1/files/uploads", headers=bearer(owner), json=declare(b"original")
            )
        ).json()
        assert (
            await transfer.put(first["upload_url"], headers=first["headers"], content=b"original")
        ).status_code == 200
        root = f"/api/v1/files/{first['file']['id']}"
        assert (await client.post(root + "/complete", headers=bearer(owner))).status_code == 200
        payload = declare(b"")
        payload.pop("name")
        payload["base_generation"] = 1
        response = await client.post(root + "/versions", headers=bearer(owner), json=payload)
        assert response.status_code == 201, response.text
        ticket = response.json()
        assert ticket["version"]["upload_method"] == "basic"
        assert (
            await transfer.put(ticket["upload_url"], headers=ticket["headers"], content=b"")
        ).status_code == 200
        complete = await client.post(
            root + f"/versions/{ticket['version']['id']}/complete", headers=bearer(owner)
        )
        assert complete.status_code == 200, complete.text
        assert complete.json()["size_bytes"] == 0
        download = (await client.post(root + "/download-url", headers=bearer(owner))).json()
        fetched = await transfer.get(download["download_url"])
        assert fetched.status_code == 200 and fetched.content == b""
