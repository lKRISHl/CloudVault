import os
from datetime import UTC, timedelta
from uuid import UUID

import httpx
import pytest

from app.models import File, TrashEntry
from app.services.trash_cleanup import TrashCleanupService
from app.storage.base import ObjectNotFoundError, ObjectRef
from tests.api.test_auth import register_user
from tests.api.test_organizations import bearer
from tests.api.test_trash import trash
from tests.test_uploads_integration import bind, declare, storage

__all__ = ["storage"]
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_S3_ENDPOINT"), reason="Real trash tests need TEST_S3_ENDPOINT"
)


@pytest.mark.asyncio
async def test_real_upload_trash_restore_and_queued_byte_reclamation(
    client, db_factory, storage, monkeypatch
):
    owner = await register_user(client)
    await bind(storage, owner, monkeypatch)
    body = b"Real recoverable then permanently removed bytes"
    response = await client.post("/api/v1/files/uploads", headers=bearer(owner), json=declare(body))
    assert response.status_code == 201
    ticket = response.json()
    fid = ticket["file"]["id"]
    async with httpx.AsyncClient() as transfer:
        assert (
            await transfer.put(ticket["upload_url"], content=body, headers=ticket["headers"])
        ).status_code == 200
        assert (
            await client.post(f"/api/v1/files/{fid}/complete", headers=bearer(owner))
        ).status_code == 200
        first = await trash(client, owner, "files", fid)
        assert (
            await client.post(f"/api/v1/trash/{first['id']}/restore", headers=bearer(owner))
        ).status_code == 204
        grant = await client.post(f"/api/v1/files/{fid}/download-url", headers=bearer(owner))
        assert (await transfer.get(grant.json()["download_url"])).content == body
        second = await trash(client, owner, "files", fid)
        assert (
            await client.post(
                f"/api/v1/trash/{second['id']}/purge",
                headers=bearer(owner),
                json={"confirmation": "DELETE"},
            )
        ).status_code == 202
    async with db_factory() as db:
        entry = await db.get(TrashEntry, UUID(second["id"]))
        file = await db.get(File, UUID(fid))
        ref = ObjectRef(file.tenant_id, file.id, file.object_id)
        assert not await TrashCleanupService(db, storage).sweep(entry.id, entry.tenant_id)
        assert await storage.read_small(ref) == body
        later = entry.not_before.replace(tzinfo=UTC) + timedelta(hours=1)
        assert await TrashCleanupService(db, storage).sweep(entry.id, entry.tenant_id, later)
        with pytest.raises(ObjectNotFoundError):
            await storage.inspect_upload(ref)
        # Simulate a late provider write; the retained exact reference is rechecked.
        await storage.put_small(ref, body)
        assert await TrashCleanupService(db, storage).sweep(
            entry.id, entry.tenant_id, later + timedelta(minutes=1)
        )
        with pytest.raises(ObjectNotFoundError):
            await storage.inspect_upload(ref)
        assert (await db.get(File, file.id)).object_id == ref.object_id
    assert (await client.get("/api/v1/trash", headers=bearer(owner))).json()["items"] == []
