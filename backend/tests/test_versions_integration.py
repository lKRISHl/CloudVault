import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.models import FileVersion, TrashEntry, UploadIntent
from app.services.trash_cleanup import TrashCleanupService
from app.storage.base import ObjectNotFoundError, ObjectRef
from tests.api.test_auth import register_user
from tests.api.test_organizations import bearer
from tests.api.test_trash import trash
from tests.api.test_versions import declaration
from tests.test_uploads_integration import bind, declare, storage

__all__ = ["storage"]
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_S3_ENDPOINT"), reason="Real versions need TEST_S3_ENDPOINT"
)


@pytest.mark.asyncio
@pytest.mark.parametrize("multipart", [False, True])
async def test_real_versions_download_restoration_and_all_retained_bytes_purged(
    client, db_factory, storage, monkeypatch, multipart
):
    owner = await register_user(client)
    await bind(storage, owner, monkeypatch)
    from app.core.config import settings

    monkeypatch.setattr(settings, "MULTIPART_PART_BYTES", 5 * 1024 * 1024)
    a, b = b"Original exact bytes", b"Replacement distinct bytes"
    async with httpx.AsyncClient() as transfer:
        metadata = declare(a)
        if multipart:
            checksum = metadata.pop("checksum_sha256")
            response = await client.post(
                "/api/v1/files/multipart/uploads",
                headers=bearer(owner),
                json={**metadata, "part_size": 5 * 1024 * 1024, "checksums": [checksum]},
            )
            assert response.status_code == 201, response.text
            initial = response.json()
            grant = initial["parts"][0]
        else:
            initial = (
                await client.post("/api/v1/files/uploads", headers=bearer(owner), json=metadata)
            ).json()
            grant = initial
        assert (
            await transfer.put(grant["upload_url"], headers=grant["headers"], content=a)
        ).status_code == 200
        fid = initial["file"]["id"]
        assert (
            await client.post(
                f"/api/v1/files/{fid}/{'multipart/complete' if multipart else 'complete'}",
                headers=bearer(owner),
            )
        ).status_code == 200
        root = f"/api/v1/files/{fid}/versions"
        first = (await client.get(root, headers=bearer(owner))).json()["items"][0]
        ticket = (await client.post(root, headers=bearer(owner), json=declaration(body=b))).json()
        assert (
            await transfer.put(ticket["upload_url"], headers=ticket["headers"], content=b)
        ).status_code == 200
        assert (
            await client.post(root + f"/{ticket['version']['id']}/complete", headers=bearer(owner))
        ).status_code == 200
        if multipart:
            from app.jobs import cleanup_uploads

            async with db_factory() as db:
                intent = await db.get(UploadIntent, UUID(fid))
                intent.expires_at = datetime.now(UTC) - timedelta(days=1)
                await db.commit()

            class Borrowed:
                def __getattr__(self, name):
                    return getattr(storage, name)

                async def close(self):
                    pass

            monkeypatch.setattr(cleanup_uploads, "S3ObjectStorage", lambda *_: Borrowed())
            await cleanup_uploads.tick(db_factory)
        for version, expected in [(first, a), (ticket["version"], b)]:
            grant = await client.post(
                root + f"/{version['id']}/download-url", headers=bearer(owner)
            )
            assert grant.status_code == 200, grant.text
            assert (await transfer.get(grant.json()["download_url"])).content == expected
        restored = await client.post(
            root + f"/{first['id']}/restore", headers=bearer(owner), json={"base_generation": 2}
        )
        assert restored.status_code == 200
        grant = await client.post(f"/api/v1/files/{fid}/download-url", headers=bearer(owner))
        assert (await transfer.get(grant.json()["download_url"])).content == a
    entry = await trash(client, owner, "files", fid)
    await client.post(
        f"/api/v1/trash/{entry['id']}/purge", headers=bearer(owner), json={"confirmation": "DELETE"}
    )
    async with db_factory() as db:
        row = await db.get(TrashEntry, UUID(entry["id"]))
        eid, tenant = row.id, row.tenant_id
        await db.rollback()
        assert await TrashCleanupService(db, storage).sweep(
            eid, tenant, datetime.now(UTC) + timedelta(days=2)
        )
        versions = list(
            await db.scalars(select(FileVersion).where(FileVersion.file_id == UUID(fid)))
        )
        for version in versions:
            with pytest.raises(ObjectNotFoundError):
                await storage.inspect_upload(ObjectRef(tenant, UUID(fid), version.object_id))
            assert version.purged_at
