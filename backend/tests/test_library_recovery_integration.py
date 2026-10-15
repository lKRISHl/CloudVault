import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.models import File, FileVersion
from app.services.trash_cleanup import TrashCleanupService
from app.storage.base import ObjectNotFoundError, ObjectRef
from tests.api.test_auth import register_user
from tests.api.test_folders import create as folder
from tests.api.test_library_recovery import move, restore
from tests.api.test_organizations import bearer
from tests.api.test_trash import trash
from tests.test_uploads_integration import bind, declare, storage

__all__ = ["storage"]
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_S3_ENDPOINT"), reason="Real recovery needs TEST_S3_ENDPOINT"
)


@pytest.mark.asyncio
@pytest.mark.parametrize("multipart", [False, True])
async def test_real_moves_recovery_and_cancelled_subtree_cleanup_preserve_exact_bytes(
    client, db_factory, storage, monkeypatch, multipart
):
    owner = await register_user(client)
    await bind(storage, owner, monkeypatch)
    source = await folder(client, owner, "Source")
    target = await folder(client, owner, "Target")
    body = b"Content survives file movement and explicit recovery"
    async with httpx.AsyncClient(timeout=30) as transfer:
        ticket = (
            await client.post(
                "/api/v1/files/uploads",
                headers=bearer(owner),
                json={**declare(body), "folder_id": source["id"]},
            )
        ).json()
        assert (
            await transfer.put(ticket["upload_url"], headers=ticket["headers"], content=body)
        ).status_code == 200
        fid = ticket["file"]["id"]
        assert (
            await client.post(f"/api/v1/files/{fid}/complete", headers=bearer(owner))
        ).status_code == 200
        async with db_factory() as db:
            original = await db.scalar(select(FileVersion).where(FileVersion.file_id == UUID(fid)))
            original_id, object_id = original.id, original.object_id
        assert (await move(client, owner, fid, target["id"], source["id"])).status_code == 200
        entry = await trash(client, owner, "files", fid)
        assert (
            await restore(client, owner, entry, target["id"], "Recovered.txt")
        ).status_code == 204
        grant = (
            await client.post(
                f"/api/v1/files/{fid}/versions/{original_id}/download-url", headers=bearer(owner)
            )
        ).json()
        fetched = await transfer.get(grant["download_url"])
        assert fetched.status_code == 200 and fetched.content == body
        assert "Recovered.txt" in fetched.headers["content-disposition"]
        async with db_factory() as db:
            assert (await db.get(File, UUID(fid))).object_id == object_id
        pending_body = b"Cancelled bytes must be reclaimed safely"
        pending_payload = {**declare(pending_body, "Pending.txt"), "folder_id": source["id"]}
        if multipart:
            checksum = pending_payload.pop("checksum_sha256")
            pending_payload.update(part_size=8388608, checksums=[checksum])
        response = await client.post(
            "/api/v1/files/multipart/uploads" if multipart else "/api/v1/files/uploads",
            headers=bearer(owner),
            json=pending_payload,
        )
        assert response.status_code == 201, response.text
        pending = response.json()
        grant = pending["parts"][0] if multipart else pending
        if multipart:
            assert (
                await transfer.put(
                    grant["upload_url"], headers=grant["headers"], content=pending_body
                )
            ).status_code == 200
        response = await client.post(
            f"/api/v1/folders/{source['id']}/cancel-uploads-and-trash",
            headers=bearer(owner),
            json={"confirmation": "CANCEL UPLOADS"},
        )
        assert response.status_code == 201, response.text
        entry = response.json()
        if not multipart:
            # A capability already issued before cancellation can still store bytes.
            assert (
                await transfer.put(
                    grant["upload_url"], headers=grant["headers"], content=pending_body
                )
            ).status_code == 200
        assert (
            await client.post(
                f"/api/v1/trash/{entry['id']}/purge",
                headers=bearer(owner),
                json={"confirmation": "DELETE"},
            )
        ).status_code == 202
        async with db_factory() as db:
            row = await db.get(File, UUID(pending["file"]["id"]))
            ref = ObjectRef(row.tenant_id, row.id, row.object_id)
            tenant, eid = row.tenant_id, UUID(entry["id"])
            await db.rollback()
            assert not await TrashCleanupService(db, storage).sweep(eid, tenant)
            later = datetime.now(UTC) + timedelta(days=2)
            assert await TrashCleanupService(db, storage).sweep(eid, tenant, later)
            assert not await storage.pending_for_object(ref)
            with pytest.raises(ObjectNotFoundError):
                await storage.inspect_upload(ref)
            assert await storage.read_small(ObjectRef(tenant, UUID(fid), object_id)) == body
