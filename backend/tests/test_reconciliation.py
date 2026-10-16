from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import File, FileVersion, UploadIntent
from app.services.reconciliation import ReconciliationService
from app.storage.base import ObjectNotFoundError, StorageError
from tests.api.test_auth import register_user
from tests.api.test_files import reserve
from tests.api.test_uploads import DIGEST


class Provider:
    client = SimpleNamespace(get_bucket_versioning="versioning")

    def __init__(self):
        self.objects, self.deleted = set(), []
        self.fail = False
        self.versioning = {}

    async def call(self, operation):
        assert operation == "versioning"
        return self.versioning

    async def pending_for_object(self, ref):
        return []

    async def delete(self, ref):
        self.objects.discard(ref.key)
        self.deleted.append(ref.key)
        if self.fail:
            raise StorageError("private lost acknowledgement")

    async def inspect_upload(self, ref):
        if ref.key not in self.objects:
            raise ObjectNotFoundError("missing")
        return object()


async def legacy(client, db_factory, monkeypatch):
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "reconcile-unit")
    owner = await register_user(client)
    file = await reserve(db_factory, owner, "Contradictory.txt")
    tenant = UUID(owner["user"]["tenant"]["id"])
    now = datetime.now(UTC)
    async with db_factory() as db:
        intent = UploadIntent(
            file_id=file.id,
            tenant_id=tenant,
            created_by=UUID(owner["user"]["id"]),
            object_id=uuid4(),
            request_id=uuid4(),
            storage_bucket="reconcile-unit",
            fingerprint="0" * 64,
            expires_at=now + timedelta(hours=1),
        )
        version = FileVersion(
            file_id=file.id,
            tenant_id=tenant,
            created_by=UUID(owner["user"]["id"]),
            number=1,
            request_id=uuid4(),
            object_id=uuid4(),
            storage_bucket="reconcile-unit",
            declared_size_bytes=1,
            expected_checksum_sha256=DIGEST,
            upload_expires_at=now + timedelta(hours=2),
        )
        db.add_all([intent, version])
        await db.commit()
    return file.id, tenant, now


@pytest.mark.asyncio
async def test_operator_inventory_waits_then_retains_refs_across_lost_ack_and_late_write(
    client,
    db_factory,
    monkeypatch,
):
    file_id, tenant, now = await legacy(client, db_factory, monkeypatch)
    provider = Provider()
    async with db_factory() as db:
        service = ReconciliationService(db, provider)
        inventory = await service.diagnose(tenant, file_id)
        assert inventory["retirement_allowed"]
        assert {item["kind"] for item in inventory["references"]} == {"intent", "version"}
        assert len({item["key"] for item in inventory["references"]}) == 2
        await db.rollback()
        assert await service.retire(tenant, file_id, confirmed_file_id=file_id, now=now) == (
            "waiting_for_original_deadlines"
        )
        assert not provider.deleted
        intent = await db.get(UploadIntent, file_id)
        assert intent.cancelled_at and intent.expires_at.replace(tzinfo=UTC) == now + timedelta(
            hours=1
        )
        await db.rollback()
        provider.fail = True
        with pytest.raises(StorageError):
            await service.retire(
                tenant, file_id, confirmed_file_id=file_id, now=now + timedelta(hours=3)
            )
        await db.rollback()
        assert (await db.get(File, file_id)).upload_cleanup_at is None
        assert (await db.get(UploadIntent, file_id)).cancelled_at
        assert await db.scalar(select(FileVersion.id).where(FileVersion.file_id == file_id))
        await db.rollback()
        provider.fail = False
        assert await service.retire(
            tenant, file_id, confirmed_file_id=file_id, now=now + timedelta(hours=3)
        ) == ("retired_references_retained")
        assert (await db.get(File, file_id)).upload_cleanup_at
        assert (await db.get(File, file_id)).object_id is None
        version = await db.scalar(select(FileVersion).where(FileVersion.file_id == file_id))
        assert version.cleaned_at and version.cancelled_at
        assert await db.get(UploadIntent, file_id)
        await db.rollback()
        provider.objects = {item["key"] for item in inventory["references"]}
        await service.retire(
            tenant, file_id, confirmed_file_id=file_id, now=now + timedelta(hours=4)
        )
        assert not provider.objects


@pytest.mark.asyncio
async def test_reconciliation_refuses_wrong_tenant_confirmation_provider_and_completed_ref(
    client,
    db_factory,
    monkeypatch,
):
    file_id, tenant, now = await legacy(client, db_factory, monkeypatch)
    provider = Provider()
    async with db_factory() as db:
        service = ReconciliationService(db, provider)
        with pytest.raises(ValueError, match="confirmation"):
            await service.retire(tenant, file_id, confirmed_file_id=uuid4())
        with pytest.raises(ValueError, match="selected tenant"):
            await service.diagnose(uuid4(), file_id)
        await db.rollback()
        monkeypatch.setattr(settings, "S3_BUCKET_NAME", "changed-bucket")
        with pytest.raises(ValueError, match="configuration changed"):
            await service.retire(tenant, file_id, confirmed_file_id=file_id)
        await db.rollback()
        assert (await db.get(UploadIntent, file_id)).cancelled_at is None
        monkeypatch.setattr(settings, "S3_BUCKET_NAME", "reconcile-unit")
        version = await db.scalar(select(FileVersion).where(FileVersion.file_id == file_id))
        version.status = "uploaded"
        version.size_bytes = 1
        version.checksum_sha256 = DIGEST
        version.content_type = "application/octet-stream"
        version.storage_etag = '"retained"'
        version.completed_at = now
        await db.commit()
        with pytest.raises(ValueError, match="completed content"):
            await service.retire(tenant, file_id, confirmed_file_id=file_id)
        assert not provider.deleted


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["Enabled", "Suspended"])
async def test_reconciliation_refuses_versioned_byte_purge(client, db_factory, monkeypatch, status):
    file_id, tenant, now = await legacy(client, db_factory, monkeypatch)
    provider = Provider()
    provider.versioning = {"Status": status}
    async with db_factory() as db:
        with pytest.raises(StorageError, match="unversioned"):
            await ReconciliationService(db, provider).retire(
                tenant,
                file_id,
                confirmed_file_id=file_id,
                now=now + timedelta(hours=3),
            )
    assert not provider.deleted


@pytest.mark.asyncio
async def test_adoption_requires_manager_and_matching_provider_then_records_real_version(
    client,
    db_factory,
    monkeypatch,
):
    from fastapi import HTTPException

    from app.models import FileVersionChange, Membership, TrashEntry, UserRole

    file_id, tenant, now = await legacy(client, db_factory, monkeypatch)
    async with db_factory() as db:
        file = await db.get(File, file_id)
        manager = file.created_by
        version = await db.scalar(select(FileVersion).where(FileVersion.file_id == file_id))
        version.status = "uploaded"
        version.size_bytes = 1
        version.checksum_sha256 = DIGEST
        version.content_type = "application/octet-stream"
        version.storage_etag = '"retained"'
        version.completed_at = now
        version_id, object_id = version.id, version.object_id
        await db.commit()
    # DB operator credentials alone cannot invent an active workspace identity.
    async with db_factory() as db:
        with pytest.raises(HTTPException):
            await ReconciliationService(db, Provider()).adopt(
                tenant,
                file_id,
                version_id,
                uuid4(),
                confirmed_file_id=file_id,
            )

    class Retained(Provider):
        checksum = "changed"

        async def inspect_upload(self, ref):
            assert ref.tenant_id == tenant and ref.file_id == file_id and ref.object_id == object_id
            return SimpleNamespace(
                size_bytes=1,
                checksum_sha256=self.checksum,
                etag='"retained"',
                content_type="application/octet-stream",
            )

    provider = Retained()
    async with db_factory() as db:
        membership = await db.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant,
                Membership.user_id == manager,
            )
        )
        membership.role = UserRole.MEMBER
        await db.commit()
        with pytest.raises(ValueError, match="workspace manager"):
            await ReconciliationService(db, provider).adopt(
                tenant,
                file_id,
                version_id,
                manager,
                confirmed_file_id=file_id,
            )
        await db.rollback()
        membership = await db.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant,
                Membership.user_id == manager,
            )
        )
        membership.role = UserRole.OWNER
        await db.commit()
    async with db_factory() as db:
        with pytest.raises(ValueError, match="differs"):
            await ReconciliationService(db, provider).adopt(
                tenant,
                file_id,
                version_id,
                manager,
                confirmed_file_id=file_id,
            )
        await db.rollback()
        assert (await db.get(File, file_id)).object_id is None
    provider.checksum = DIGEST
    async with db_factory() as db:
        entry = TrashEntry(
            tenant_id=tenant,
            root_id=file_id,
            kind="files",
            trashed_by=manager,
            retain_until=now + timedelta(days=30),
            not_before=now + timedelta(hours=3),
        )
        db.add(entry)
        await db.flush()
        file = await db.get(File, file_id)
        file.trash_id = entry.id
        await db.commit()
        with pytest.raises(ValueError, match="live legacy"):
            await ReconciliationService(db, provider).adopt(
                tenant,
                file_id,
                version_id,
                manager,
                confirmed_file_id=file_id,
            )
        await db.rollback()
        file = await db.get(File, file_id)
        file.trash_id = None
        await db.commit()
    async with db_factory() as db:
        assert (
            await ReconciliationService(db, provider).adopt(
                tenant,
                file_id,
                version_id,
                manager,
                confirmed_file_id=file_id,
            )
            == "adopted_verified_version_references_retained"
        )
        file = await db.get(File, file_id)
        assert file.status == "uploaded" and file.object_id == object_id and file.size_bytes == 1
        assert file.current_version == 1 and file.version_generation == 2
        assert (await db.get(UploadIntent, file_id)).cancelled_at
        change = await db.scalar(
            select(FileVersionChange).where(FileVersionChange.file_id == file_id)
        )
        assert change.actor_id == manager and change.reason == "restore"
    assert provider.deleted == []


@pytest.mark.asyncio
async def test_operator_cancels_unknown_location_intent_without_materialized_metadata(
    db_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "reconcile-unit")
    tenant, file_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    async with db_factory() as db:
        db.add(
            UploadIntent(
                file_id=file_id,
                tenant_id=tenant,
                created_by=uuid4(),
                object_id=uuid4(),
                request_id=uuid4(),
                storage_bucket="reconcile-unit",
                fingerprint="0" * 64,
                expires_at=now - timedelta(hours=3),
            )
        )
        await db.commit()
        service = ReconciliationService(db, Provider())
        diagnosis = await service.diagnose(tenant, file_id)
        assert diagnosis["metadata_status"] == "unmaterialized" and diagnosis["folder_id"] is None
        await db.rollback()
        assert await service.retire(tenant, file_id, confirmed_file_id=file_id, now=now) == (
            "retired_references_retained"
        )
        assert (await db.get(UploadIntent, file_id)).cancelled_at
        assert await db.get(File, file_id) is None


@pytest.mark.asyncio
async def test_operator_inventory_pages_all_refs_and_retires_large_history_in_bounded_passes(
    client,
    db_factory,
    monkeypatch,
):
    file_id, tenant, now = await legacy(client, db_factory, monkeypatch)
    async with db_factory() as db:
        intent = await db.get(UploadIntent, file_id)
        for number in range(2, 102):
            db.add(
                FileVersion(
                    file_id=file_id,
                    tenant_id=tenant,
                    created_by=intent.created_by,
                    number=number,
                    request_id=uuid4(),
                    object_id=uuid4(),
                    storage_bucket="reconcile-unit",
                    declared_size_bytes=1,
                    expected_checksum_sha256=DIGEST,
                    upload_expires_at=now + timedelta(hours=5) if number == 101 else now,
                )
            )
        await db.commit()
        provider = Provider()
        service = ReconciliationService(db, provider)
        offset, identities = 0, []
        while offset is not None:
            result = await service.diagnose(tenant, file_id, offset=offset)
            identities.extend(
                item["version_id"] for item in result["references"] if item["kind"] == "version"
            )
            assert len(result["references"]) <= 26 and result["retirement_allowed"] is None
            offset = result["next_version_offset"]
        assert len(identities) == len(set(identities)) == 101
        await db.rollback()
        assert await service.retire(
            tenant, file_id, confirmed_file_id=file_id, now=now + timedelta(hours=3)
        ) == ("waiting_for_original_deadlines")
        assert not provider.deleted
        states = []
        for _ in range(30):
            before = len(provider.deleted)
            state = await service.retire(
                tenant,
                file_id,
                confirmed_file_id=file_id,
                now=now + timedelta(hours=6),
            )
            assert len(provider.deleted) - before <= settings.STORAGE_STAGE_BATCH_SIZE + 1
            states.append(state)
            if state == "retired_references_retained":
                break
        assert len(states) == 21 and states[-1] == "retired_references_retained"
        assert set(states[:-1]) == {"cleanup_in_progress"}
        assert (await db.get(File, file_id)).upload_cleanup_at
        assert len(set(provider.deleted)) == 102  # All 101 version keys and the intent.
