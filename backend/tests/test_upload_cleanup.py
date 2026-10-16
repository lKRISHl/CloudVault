from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.core.config import settings
from app.jobs import cleanup_uploads
from app.models import File
from app.services.upload_cleanup import UploadCleanupService
from app.storage.base import MultipartNotFoundError, StorageError
from tests.api import test_multipart
from tests.api.test_auth import register_user
from tests.api.test_multipart import HASHES, ROOT, ContractMultipart, start
from tests.api.test_organizations import bearer

storage = test_multipart.storage


class CleanupContract(ContractMultipart):
    async def pending_for_object(self, ref):
        return []

    async def abort_multipart(self, ref, upload_id):
        if self.error:
            raise self.error
        await super().abort_multipart(ref, upload_id)

    async def delete(self, ref):
        if self.error:
            raise self.error
        self.objects.pop(ref.file_id, None)

    async def list_parts(self, ref, upload_id):
        if self.error:
            raise self.error
        if ref.file_id in self.aborted:
            raise MultipartNotFoundError("aborted")
        return await super().list_parts(ref, upload_id)


@pytest.mark.asyncio
async def test_cleanup_waits_for_expiry_retains_references_and_releases_names(
    client, db_factory, storage
):
    owner = await register_user(client)
    ticket = await start(client, owner)
    id, tenant = UUID(ticket["file"]["id"]), UUID(owner["user"]["tenant"]["id"])
    now = datetime.now(UTC)
    provider = CleanupContract()
    async with db_factory() as db:
        assert not await UploadCleanupService(db, provider).sweep(id, tenant, now)
        file = await db.get(File, id)
        original_object = file.object_id
        file.upload_expires_at = now - timedelta(hours=2)
        await db.commit()
        assert await UploadCleanupService(db, provider).sweep(id, tenant, now)
        await db.refresh(file)
        assert file.upload_cleanup_at and file.object_id == original_object
        assert file.multipart_state == "aborted"
    assert (await client.get(f"{ROOT}/{id}", headers=bearer(owner))).status_code == 404
    assert not (await client.get(ROOT, headers=bearer(owner))).json()["items"]
    replacement = await start(client, owner)
    assert replacement["file"]["id"] != str(id)
    assert (
        await client.post(
            f"{ROOT}/{id}/multipart/resume", headers=bearer(owner), json={"checksums": HASHES}
        )
    ).status_code == 404
    async with db_factory() as db:
        # Repeat sweeps retain tombstones and continue cleanup without touching replacement.
        assert await UploadCleanupService(db, provider).sweep(
            id, tenant, now + timedelta(minutes=1)
        )
        assert (await db.get(File, UUID(replacement["file"]["id"]))).upload_cleanup_at is None


@pytest.mark.asyncio
async def test_failed_cleanup_keeps_name_and_completed_or_foreign_files_untouched(
    client, db_factory, storage
):
    owner = await register_user(client)
    ticket = await start(client, owner)
    id, tenant = UUID(ticket["file"]["id"]), UUID(owner["user"]["tenant"]["id"])
    provider = CleanupContract()
    provider.error = StorageError("provider unavailable")
    async with db_factory() as db:
        file = await db.get(File, id)
        file.upload_expires_at = datetime.now(UTC) - timedelta(hours=2)
        await db.commit()
        assert not await UploadCleanupService(db, provider).sweep(id, uuid4())
        assert not await UploadCleanupService(db, provider).sweep(id, tenant)
        await db.refresh(file)
        assert file.upload_cleanup_at is None and file.upload_cleanup_checked_at is not None
    assert (await client.get(ROOT, headers=bearer(owner))).json()["items"][0]["id"] == str(id)
    storage.received(ticket)
    async with db_factory() as db:
        file = await db.get(File, id)
        file.upload_expires_at = datetime.now(UTC) + timedelta(hours=1)
        await db.commit()
    assert (
        await client.post(f"{ROOT}/{id}/multipart/complete", headers=bearer(owner))
    ).status_code == 200
    async with db_factory() as db:
        assert not await UploadCleanupService(db, provider).sweep(
            id, tenant, datetime.now(UTC) + timedelta(days=1)
        )
    assert id not in provider.aborted


@pytest.mark.asyncio
async def test_versioned_bucket_cleanup_fails_closed(monkeypatch):
    class Inventory:
        client = SimpleNamespace(get_bucket_versioning="versioning")

        async def call(self, operation):
            assert operation == "versioning"
            return {"Status": "Enabled"}

        async def close(self):
            pass

    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "cv-versioned")
    monkeypatch.setattr(cleanup_uploads, "S3ObjectStorage", lambda *_: Inventory())
    with pytest.raises(StorageError, match="unversioned"):
        await cleanup_uploads.tick()


@pytest.mark.asyncio
async def test_orphan_scan_skips_live_known_recent_and_nonmanaged_keys(
    client, db_factory, storage, monkeypatch
):
    owner = await register_user(client)
    ticket = await start(client, owner)
    async with db_factory() as db:
        file = await db.get(File, UUID(ticket["file"]["id"]))
        known_key = f"tenants/{file.tenant_id}/files/{file.id}/objects/{file.object_id}"
        known_id = file.multipart_upload_id
    now = datetime.now(UTC)
    orphan_ref = cleanup_uploads.managed_ref(f"tenants/{uuid4()}/files/{uuid4()}/objects/{uuid4()}")
    aborted = []

    class Inventory:
        client = SimpleNamespace(list_multipart_uploads="list")

        async def call(self, operation, **params):
            assert params == {"Prefix": "", "MaxUploads": 100}
            return {
                "Uploads": [
                    {"Key": known_key, "UploadId": known_id, "Initiated": now - timedelta(days=1)},
                    {
                        "Key": orphan_ref.key,
                        "UploadId": "unknown-old",
                        "Initiated": now - timedelta(days=1),
                    },
                    {"Key": orphan_ref.key, "UploadId": "unknown-new", "Initiated": now},
                    {
                        "Key": "other-app/file",
                        "UploadId": "external",
                        "Initiated": now - timedelta(days=1),
                    },
                ]
            }

    class Scoped:
        def __init__(self, config, tenant_id):
            assert tenant_id == orphan_ref.tenant_id

        async def abort_multipart(self, ref, upload_id):
            assert ref == orphan_ref
            aborted.append(upload_id)

        async def close(self):
            pass

    monkeypatch.setattr(cleanup_uploads, "S3ObjectStorage", Scoped)
    assert await cleanup_uploads.sweep_orphans(Inventory(), db_factory, now=now) is None
    assert aborted == ["unknown-old"]


@pytest.mark.asyncio
async def test_bounded_upload_stage_reduces_unconfirmed_backlog_and_rotates(
    client,
    db_factory,
    storage,
    monkeypatch,
):
    from app.services.job_backlog import backlog

    owner = await register_user(client)
    tickets = [await start(client, owner, name=f"bounded-{i}.bin") for i in range(3)]
    now = datetime.now(UTC)
    async with db_factory() as db:
        for ticket in tickets:
            file = await db.get(File, UUID(ticket["file"]["id"]))
            file.upload_expires_at = now - timedelta(hours=3)
        await db.commit()

    class Provider(CleanupContract):
        client = SimpleNamespace(get_bucket_versioning="versioning")

        async def call(self, operation):
            assert operation == "versioning"
            return {}

        async def close(self):
            pass

    provider = Provider()
    monkeypatch.setattr(cleanup_uploads, "S3ObjectStorage", lambda *_: provider)
    assert (await backlog(db_factory, "storage"))["unconfirmed_expired_uploads"]["count"] == 3
    report = {}
    await cleanup_uploads.tick(db_factory, stage="uploads", batch_size=2, report=report)
    assert report == {"inspected": 2, "deferred": 0}
    assert (await backlog(db_factory, "storage"))["unconfirmed_expired_uploads"]["count"] == 1
    await cleanup_uploads.tick(db_factory, stage="uploads", batch_size=2)
    assert (await backlog(db_factory, "storage"))["unconfirmed_expired_uploads"]["count"] == 0
    assert len(set(provider.aborted)) == 3
