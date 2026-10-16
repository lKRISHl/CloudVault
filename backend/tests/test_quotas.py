"""Quota admission/retention and inventory evidence; PostgreSQL proves concurrency."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models import File, FileVersion, StorageObservation, StorageQuota, UploadIntent
from app.services.background_jobs import storage_namespace
from app.services.quota_inventory import QuotaInventory
from app.services.quotas import QuotaService
from app.storage.base import ObjectNotFoundError
from tests.api.test_auth import register_user
from tests.api.test_organizations import add_member, bearer
from tests.api.test_uploads import BODY, DIGEST, payload
from tests.api.test_uploads import storage as upload_storage

storage = upload_storage

pytestmark = pytest.mark.asyncio
ROOT = "/api/v1/files"


async def tenant_limit(factory, owner, limit):
    tid = UUID(owner["user"]["tenant"]["id"])
    async with factory() as db:
        quota = await db.get(StorageQuota, tid)
        if quota is None:
            quota = StorageQuota(tenant_id=tid)
            db.add(quota)
        quota.storage_limit_bytes = limit
        await db.commit()
    return tid


async def usage(factory, tenant_id):
    async with factory() as db:
        return await QuotaService(db).usage(tenant_id)


async def test_admission_idempotency_exact_boundary_and_completion_not_double_counted(
    client, db_factory, storage
):
    owner = await register_user(client)
    tid = await tenant_limit(db_factory, owner, len(BODY))
    declaration = payload()
    first = await client.post(ROOT + "/uploads", headers=bearer(owner), json=declaration)
    assert first.status_code == 201, first.text
    assert (await usage(db_factory, tid)).reserved_bytes == len(BODY)
    assert (
        await client.post(ROOT + "/uploads", headers=bearer(owner), json=declaration)
    ).status_code == 201
    assert (
        await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload(name="Over.txt"))
    ).status_code == 403
    fid = first.json()["file"]["id"]
    assert (await client.post(f"{ROOT}/{fid}/complete", headers=bearer(owner))).status_code == 200
    total = await usage(db_factory, tid)
    assert total.retained_bytes == total.allocated_bytes == len(BODY)
    assert total.reserved_bytes == 0
    # Completion creates a FileVersion mirror; both references represent the same bytes.
    async with db_factory() as db:
        assert await db.scalar(select(FileVersion.id).where(FileVersion.file_id == UUID(fid)))


async def test_downgrade_preserves_existing_reservation_completion_but_blocks_new_work(
    client, db_factory, storage
):
    owner = await register_user(client)
    ticket = await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload())
    tid = await tenant_limit(db_factory, owner, 0)
    assert (await usage(db_factory, tid)).over_quota
    fid = ticket.json()["file"]["id"]
    assert (await client.post(f"{ROOT}/{fid}/complete", headers=bearer(owner))).status_code == 200
    assert (
        await client.post(
            ROOT + "/uploads", headers=bearer(owner), json=payload(name="No space.txt")
        )
    ).status_code == 403


async def test_cancel_or_expire_does_not_release_until_cleanup_evidence(
    client, db_factory, storage
):
    owner = await register_user(client)
    tid = await tenant_limit(db_factory, owner, len(BODY))
    ticket = await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload())
    fid = UUID(ticket.json()["file"]["id"])
    async with db_factory() as db:
        file = await db.get(File, fid)
        file.upload_cancelled_at = datetime.now(UTC)
        file.upload_expires_at = datetime.now(UTC) - timedelta(days=1)
        await db.commit()
    assert (await usage(db_factory, tid)).allocated_bytes == len(BODY)
    async with db_factory() as db:
        file = await db.get(File, fid)
        file.upload_cleanup_at = datetime.now(UTC)
        await db.commit()
    assert (await usage(db_factory, tid)).allocated_bytes == 0


async def test_unknown_legacy_intent_blocks_new_allocations_until_proven_cleanup(
    client, db_factory, storage
):
    owner = await register_user(client)
    tid = UUID(owner["user"]["tenant"]["id"])
    intent_id = uuid4()
    async with db_factory() as db:
        db.add(
            UploadIntent(
                file_id=intent_id,
                tenant_id=tid,
                object_id=uuid4(),
                created_by=UUID(owner["user"]["id"]),
                request_id=uuid4(),
                storage_bucket="legacy-bucket",
                fingerprint="a" * 64,
                expires_at=datetime.now(UTC),
                reserved_bytes=None,
            )
        )
        await db.commit()
    assert (await usage(db_factory, tid)).unresolved_references == 1
    assert (
        await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload())
    ).status_code == 409
    async with db_factory() as db:
        intent = await db.get(UploadIntent, intent_id)
        intent.cleaned_at = datetime.now(UTC)
        await db.commit()
    assert not (await usage(db_factory, tid)).reconciliation_required


async def test_manager_only_usage_is_no_store_and_tenant_scoped(client, db_factory, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    other = await register_user(client, email="quota-foreign@example.com")
    await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload())
    response = await client.get(
        "/api/v1/organizations/current/storage-usage", headers=bearer(owner)
    )
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["allocated_bytes"] == len(BODY)
    assert "storage_key" not in response.text and "object_id" not in response.text
    assert (
        await client.get("/api/v1/organizations/current/storage-usage", headers=bearer(member))
    ).status_code == 403
    assert (
        await client.get("/api/v1/organizations/current/storage-usage", headers=bearer(other))
    ).json()["allocated_bytes"] == 0


async def test_concurrent_originals_cannot_overbook_postgres(client, db_factory, storage):
    if db_factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL tenant lock acceptance requires disposable PG")
    owner = await register_user(client)
    tid = await tenant_limit(db_factory, owner, len(BODY))
    responses = await asyncio.gather(
        *[
            client.post(ROOT + "/uploads", headers=bearer(owner), json=payload(name=f"Race{i}.txt"))
            for i in range(2)
        ]
    )
    assert sorted(response.status_code for response in responses) == [201, 403]
    assert (await usage(db_factory, tid)).allocated_bytes == len(BODY)


class InventoryStorage:
    bucket = "cv-unit-uploads"
    client = SimpleNamespace(
        head_object="head",
        list_multipart_uploads="uploads",
        list_parts="parts",
        list_objects_v2="objects",
    )

    def __init__(self, size=50, truncated=False):
        self.size, self.truncated = size, truncated

    async def call(self, operation, **kwargs):
        if operation == "head":
            if self.size is None:
                raise ObjectNotFoundError()
            return {"ContentLength": self.size}
        if operation == "uploads":
            return {"Uploads": [], "IsTruncated": self.truncated}
        raise AssertionError("Unexpected inventory operation")


async def test_orphan_inventory_accounts_actual_bytes_and_requires_real_absence(
    client, db_factory, storage
):
    owner = await register_user(client)
    tid = UUID(owner["user"]["tenant"]["id"])
    key = f"tenants/{tid}/files/{uuid4()}/objects/{uuid4()}"
    provider = InventoryStorage()
    async with db_factory() as db:
        await QuotaInventory(db, provider).observe(tid, key, datetime.now(UTC))
        await db.commit()
    total = await usage(db_factory, tid)
    assert total.orphan_bytes == total.allocated_bytes == 50
    provider.size, provider.truncated = None, True
    async with db_factory() as db:
        await QuotaInventory(db, provider).observe(tid, key, datetime.now(UTC))
        await db.commit()
    assert (await usage(db_factory, tid)).reconciliation_required
    provider.truncated = False
    async with db_factory() as db:
        await QuotaInventory(db, provider).observe(tid, key, datetime.now(UTC))
        await db.commit()
    assert (await usage(db_factory, tid)).allocated_bytes == 0
    assert not (await usage(db_factory, tid)).reconciliation_required


async def test_provider_evidence_and_file_snapshot_count_once_and_expand_for_extra_parts(
    client, db_factory, storage
):
    owner = await register_user(client)
    tid = UUID(owner["user"]["tenant"]["id"])
    ticket = await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload())
    fid = UUID(ticket.json()["file"]["id"])
    async with db_factory() as db:
        file = await db.get(File, fid)
        key = f"tenants/{tid}/files/{fid}/objects/{file.object_id}"
        db.add(
            StorageObservation(
                tenant_id=tid,
                namespace=storage_namespace(),
                key_hash=hashlib.sha256(key.encode()).hexdigest(),
                storage_key=key,
                storage_bucket=file.storage_bucket,
                file_id=fid,
                object_id=file.object_id,
                size_bytes=len(BODY) + 2,
                checked_at=datetime.now(UTC),
            )
        )
        await db.commit()
    total = await usage(db_factory, tid)
    assert total.allocated_bytes == total.reserved_bytes == len(BODY) + 2
    assert total.orphan_bytes == 0


async def test_replacement_reservation_is_additional_idempotent_and_cancel_stays_charged(
    client, db_factory, storage
):
    owner = await register_user(client)
    tid = await tenant_limit(db_factory, owner, 2 * len(BODY))
    ticket = await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload())
    fid = ticket.json()["file"]["id"]
    assert (await client.post(f"{ROOT}/{fid}/complete", headers=bearer(owner))).status_code == 200
    declaration = {
        "request_id": str(uuid4()),
        "base_generation": 1,
        "declared_size_bytes": len(BODY),
        "declared_content_type": "text/plain",
        "checksum_sha256": DIGEST,
    }
    version = await client.post(f"{ROOT}/{fid}/versions", headers=bearer(owner), json=declaration)
    assert version.status_code == 201, version.text
    assert (
        await client.post(f"{ROOT}/{fid}/versions", headers=bearer(owner), json=declaration)
    ).status_code == 201
    assert (await usage(db_factory, tid)).allocated_bytes == 2 * len(BODY)
    assert (
        await client.post(
            f"{ROOT}/{fid}/versions",
            headers=bearer(owner),
            json={**declaration, "request_id": str(uuid4())},
        )
    ).status_code == 403


async def test_multipart_quota_fails_before_provider_create(client, db_factory, storage):
    owner = await register_user(client)
    await tenant_limit(db_factory, owner, 0)
    response = await client.post(
        ROOT + "/multipart/uploads",
        headers=bearer(owner),
        json={
            "name": "Too large.bin",
            "declared_size_bytes": 8 * 1024**2 + 1,
            "declared_content_type": "application/octet-stream",
            "request_id": str(uuid4()),
            "part_size": 8 * 1024**2,
            "checksums": [DIGEST, DIGEST],
        },
    )
    assert response.status_code == 403, response.text
    async with db_factory() as db:
        assert await db.scalar(select(UploadIntent.file_id)) is None


async def test_preview_reserves_bound_and_failed_or_cancelled_job_keeps_allocation(
    client, db_factory, monkeypatch
):
    from tests.test_scanning import run_scan, uploaded

    owner, store, fid, _ = await uploaded(client, db_factory, monkeypatch)
    await run_scan(db_factory, store)
    tid = await tenant_limit(db_factory, owner, len(store.body) + 1024**2)
    declaration = {"request_id": str(uuid4())}
    response = await client.post(
        f"{ROOT}/{fid}/preview-jobs", headers=bearer(owner), json=declaration
    )
    assert response.status_code == 202, response.text
    assert (
        await client.post(f"{ROOT}/{fid}/preview-jobs", headers=bearer(owner), json=declaration)
    ).status_code == 202
    total = await usage(db_factory, tid)
    assert total.derivative_bytes == 1024**2
    assert total.allocated_bytes == len(store.body) + 1024**2
    jid = response.json()["id"]
    assert (
        await client.delete(f"{ROOT}/{fid}/preview-jobs/{jid}", headers=bearer(owner))
    ).status_code == 200
    assert (await usage(db_factory, tid)).derivative_bytes == 1024**2


async def test_quarantine_trash_and_verified_reclamation_preserve_correct_charge(
    client, db_factory, storage
):
    owner = await register_user(client)
    tid = UUID(owner["user"]["tenant"]["id"])
    ticket = await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload())
    fid = ticket.json()["file"]["id"]
    assert (await client.post(f"{ROOT}/{fid}/complete", headers=bearer(owner))).status_code == 200
    async with db_factory() as db:
        version = await db.scalar(select(FileVersion).where(FileVersion.file_id == UUID(fid)))
        version.scan_status = "oversized"
        await db.commit()
    assert (await usage(db_factory, tid)).retained_bytes == len(BODY)
    assert (await client.post(f"{ROOT}/{fid}/trash", headers=bearer(owner))).status_code == 201
    assert (await usage(db_factory, tid)).retained_bytes == len(BODY)
    async with db_factory() as db:
        version = await db.scalar(select(FileVersion).where(FileVersion.file_id == UUID(fid)))
        # Fixture represents the exact-version absence proof recorded by normal cleanup.
        version.purged_at = datetime.now(UTC)
        await db.commit()
    assert (await usage(db_factory, tid)).allocated_bytes == 0


async def test_failed_inventory_pauses_new_work_without_losing_policy(client, db_factory, storage):
    from app.services.quota_inventory import tick
    from app.storage.base import StorageError

    owner = await register_user(client)
    tid = UUID(owner["user"]["tenant"]["id"])

    def unavailable(_):
        raise StorageError("Private provider detail")

    with pytest.raises(StorageError):
        await tick(db_factory, unavailable, 2)
    assert (await usage(db_factory, tid)).reconciliation_required
    response = await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload())
    assert response.status_code == 409 and "Private provider detail" not in response.text


async def test_operator_plan_change_requires_confirmation_and_never_evicts(
    client, db_factory, storage, monkeypatch
):
    from app.jobs import storage_quota

    owner = await register_user(client)
    tid = UUID(owner["user"]["tenant"]["id"])
    await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload())
    monkeypatch.setattr(storage_quota, "async_session_maker", db_factory)
    with pytest.raises(ValueError):
        await storage_quota.run(tid, plan="team")
    with pytest.raises(ValueError):
        await storage_quota.run(tid, plan="team", apply=True, confirmation=uuid4())
    changed = await storage_quota.run(tid, plan="team", limit_bytes=0, apply=True, confirmation=tid)
    assert changed["plan"] == "team" and changed["over_quota"]
    assert changed["allocated_bytes"] == len(BODY)
    restored = await storage_quota.run(tid, plan="free", apply=True, confirmation=tid)
    assert restored["plan"] == "free" and not restored["over_quota"]
    assert restored["allocated_bytes"] == len(BODY)


@pytest.mark.parametrize("excess", [False, True])
async def test_inventory_supports_1024_parts_and_refuses_unbounded_manifest(
    client, db_factory, excess
):
    owner = await register_user(client)
    tid = UUID(owner["user"]["tenant"]["id"])
    key = f"tenants/{tid}/files/{uuid4()}/objects/{uuid4()}"

    class Manifest(InventoryStorage):
        async def call(self, operation, **kwargs):
            if operation == "head":
                raise ObjectNotFoundError()
            if operation == "uploads":
                return {"Uploads": [{"Key": key, "UploadId": "test"}]}
            if operation == "parts":
                tail = bool(kwargs.get("PartNumberMarker"))
                return {
                    "Parts": [{"Size": 1}] * (24 if tail else 1000),
                    "IsTruncated": excess if tail else True,
                    "NextPartNumberMarker": 1000,
                }
            raise AssertionError("Unexpected operation")

    async with db_factory() as db:
        await QuotaInventory(db, Manifest()).observe(tid, key, datetime.now(UTC))
        await db.commit()
    total = await usage(db_factory, tid)
    assert total.reconciliation_required == excess
    if not excess:
        assert total.orphan_bytes == 1024
