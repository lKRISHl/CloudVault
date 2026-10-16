"""Real provider retirement with injected acknowledgement loss after an actual delete."""

# ruff: noqa: F811 - imported pytest fixture is injected by name

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import File, FileVersion, PreviewJob, UploadIntent
from app.services.background_jobs import storage_namespace
from app.services.preview_jobs import PreviewJobService
from app.services.reconciliation import ReconciliationService
from app.storage.base import ObjectNotFoundError, ObjectRef, StorageError
from tests.test_reconciliation import legacy
from tests.test_storage_integration import storage  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_S3_ENDPOINT"), reason="Real S3 test provider required"
)


@pytest.mark.asyncio
async def test_real_retirement_lost_ack_retains_refs_and_cleans_late_bytes(
    client, db_factory, monkeypatch, storage
):
    file_id, tenant, now = await legacy(client, db_factory, monkeypatch)
    storage.tenant_id = tenant
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", storage.bucket)
    async with db_factory() as db:
        intent = await db.get(UploadIntent, file_id)
        version = await db.scalar(select(FileVersion).where(FileVersion.file_id == file_id))
        intent.storage_bucket = version.storage_bucket = storage.bucket
        await db.commit()
        service = ReconciliationService(db, storage)
        assert (
            await service.retire(tenant, file_id, confirmed_file_id=file_id)
            == "waiting_for_original_deadlines"
        )
        assert intent.cancelled_at
        # Seed already expired references; do not claim waiting hours in this test.
        intent.expires_at = version.upload_expires_at = now - timedelta(hours=3)
        refs = [ObjectRef(tenant, file_id, item.object_id) for item in (intent, version)]
        await db.commit()
        for ref in refs:
            await storage.put_small(ref, b"owned retained bytes")
        original_delete = storage.delete

        async def delete_then_lose_ack(ref):
            await original_delete(ref)
            raise StorageError("Injected lost acknowledgement after real provider deletion")

        with monkeypatch.context() as scoped:
            scoped.setattr(storage, "delete", delete_then_lose_ack)
            with pytest.raises(StorageError):
                await service.retire(tenant, file_id, confirmed_file_id=file_id)
        await db.rollback()
        assert (await db.get(UploadIntent, file_id)).cancelled_at
        assert (await db.get(File, file_id)).upload_cleanup_at is None
        assert (
            await service.retire(tenant, file_id, confirmed_file_id=file_id)
            == "retired_references_retained"
        )
        for ref in refs:
            with pytest.raises(ObjectNotFoundError):
                await storage.head(ref)
        # A late actual PUT is removed on a repeated retained-reference pass.
        for ref in refs:
            await storage.put_small(ref, b"late owned bytes")
        assert (
            await service.retire(tenant, file_id, confirmed_file_id=file_id)
            == "retired_references_retained"
        )
        for ref in refs:
            with pytest.raises(ObjectNotFoundError):
                await storage.head(ref)
        assert await db.get(UploadIntent, file_id)
        assert await db.scalar(select(FileVersion.id).where(FileVersion.file_id == file_id))


@pytest.mark.asyncio
async def test_real_preview_cleanup_keeps_ref_after_lost_ack_and_late_write(
    db_factory, monkeypatch, storage
):
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", storage.bucket)
    now = datetime.now(UTC)
    async with db_factory() as db:
        job = PreviewJob(
            tenant_id=storage.tenant_id,
            file_id=uuid4(),
            version_id=uuid4(),
            requested_by=uuid4(),
            request_id=uuid4(),
            generation=1,
            page=0,
            next_attempt_at=now - timedelta(hours=1),
            expires_at=now - timedelta(minutes=30),
            cleanup_after=now - timedelta(minutes=1),
            storage_bucket=storage.bucket,
            namespace=storage_namespace(),
        )
        db.add(job)
        await db.commit()
        identity = job.id
        service = PreviewJobService(db, storage)
        ref = service.ref(job)
        await storage.put_small(ref, b"owned derivative")
        original_delete = storage.delete

        async def delete_then_lose_ack(value):
            await original_delete(value)
            raise StorageError("Injected lost ACK after real delete")

        with monkeypatch.context() as scoped:
            scoped.setattr(storage, "delete", delete_then_lose_ack)
            assert await service.cleanup_one(job_id=identity) == "deferred"
        assert (await db.get(PreviewJob, identity, populate_existing=True)).cleanup_failed
        assert await service.cleanup_one(job_id=identity) == "cleaned_reference_retained"
        await storage.put_small(ref, b"late owned derivative")
        assert await service.cleanup_one(job_id=identity) == "cleaned_reference_retained"
        with pytest.raises(ObjectNotFoundError):
            await storage.head(ref)
        retained = await db.get(PreviewJob, identity, populate_existing=True)
        assert retained.artifact_id == ref.object_id and not retained.cleanup_failed
        # Empty disposable bucket: exercise both actual provider policy states without
        # creating versioned bytes or changing the application bucket.
        for status in ("Enabled", "Suspended"):
            await storage.call(
                storage.client.put_bucket_versioning,
                VersioningConfiguration={"Status": status},
            )
            assert await service.cleanup_one(job_id=identity) == "deferred"
            assert (await db.get(PreviewJob, identity, populate_existing=True)).cleanup_failed
