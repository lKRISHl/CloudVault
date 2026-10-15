from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.models import File, TrashEntry
from app.services.trash_cleanup import TrashCleanupService
from app.storage.base import ObjectNotFoundError, StorageError
from tests.api.test_auth import register_user
from tests.api.test_downloads import uploaded
from tests.api.test_organizations import bearer
from tests.api.test_trash import trash
from tests.api.test_uploads import storage

__all__ = ["storage"]


class PurgeStore:
    def __init__(self):
        self.client = SimpleNamespace(get_bucket_versioning=object())
        self.present = True
        self.fail = False
        self.version = None
        self.deleted = 0

    async def call(self, operation):
        return {"Status": self.version} if self.version else {}

    async def pending_for_object(self, ref):
        return []

    async def delete(self, ref):
        if self.fail:
            raise StorageError("private provider details")
        self.present = False
        self.deleted += 1

    async def inspect_upload(self, ref):
        if not self.present:
            raise ObjectNotFoundError("gone")
        return object()


@pytest.mark.asyncio
async def test_purge_waits_for_urls_then_confirms_removal_retains_references_and_retries(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    entry = await trash(client, owner, "files", fid)
    assert (
        await client.post(
            f"/api/v1/trash/{entry['id']}/purge",
            headers=bearer(owner),
            json={"confirmation": "DELETE"},
        )
    ).status_code == 202
    provider = PurgeStore()
    tenant, eid = UUID(owner["user"]["tenant"]["id"]), UUID(entry["id"])
    async with db_factory() as db:
        assert not await TrashCleanupService(db, provider).sweep(eid, tenant)
        assert provider.deleted == 0
        item = await db.get(TrashEntry, eid)
        later = item.not_before.replace(tzinfo=UTC) + timedelta(hours=1)
        provider.fail = True
        assert not await TrashCleanupService(db, provider).sweep(eid, tenant, later)
        assert (await db.get(TrashEntry, eid)).purged_at is None
        assert (await db.get(File, UUID(fid))).object_purged_at is None
        provider.fail = False
        assert await TrashCleanupService(db, provider).sweep(eid, tenant, later)
        file = await db.get(File, UUID(fid))
        assert file.object_id is not None and file.trash_id == eid and file.object_purged_at
        # A retained reference is checked again if the provider later exposes bytes.
        provider.present = True
        assert await TrashCleanupService(db, provider).sweep(
            eid, tenant, later + timedelta(minutes=1)
        )
        assert provider.deleted == 2
    assert (await client.get("/api/v1/trash", headers=bearer(owner))).json()["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["Enabled", "Suspended"])
async def test_versioned_bucket_fails_closed_and_retention_expiry_is_durable(
    client, db_factory, storage, version
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    entry = await trash(client, owner, "files", fid)
    provider = PurgeStore()
    provider.version = version
    async with db_factory() as db:
        item = await db.get(TrashEntry, UUID(entry["id"]))
        later = item.retain_until.replace(tzinfo=UTC) + timedelta(seconds=1)
        assert not await TrashCleanupService(db, provider).sweep(item.id, item.tenant_id, later)
        await db.refresh(item)
        assert (
            item.purge_requested_at is not None and item.purged_at is None and provider.deleted == 0
        )


@pytest.mark.asyncio
async def test_restored_content_never_reclaimed_by_stale_cleanup_job(client, db_factory, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    entry = await trash(client, owner, "files", fid)
    assert (
        await client.post(f"/api/v1/trash/{entry['id']}/restore", headers=bearer(owner))
    ).status_code == 204
    provider = PurgeStore()
    async with db_factory() as db:
        assert not await TrashCleanupService(db, provider).sweep(
            UUID(entry["id"]),
            UUID(owner["user"]["tenant"]["id"]),
            datetime.now(UTC) + timedelta(days=31),
        )
        assert provider.deleted == 0
