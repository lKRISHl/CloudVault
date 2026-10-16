import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api.storage import get_upload_storage
from app.core.config import settings
from app.main import app
from app.models import File, FileVersion, Membership, PreviewJob
from app.previews.worker import render
from app.schemas.previews import PreviewContent
from app.services.preview_jobs import PreviewJobService
from app.storage.base import ObjectConflictError, ObjectInfo, ObjectNotFoundError, StorageError
from tests.api.test_auth import register_user
from tests.api.test_organizations import add_member, bearer
from tests.api.test_previews import PreviewStore, complete
from tests.test_preview_renderer import image_bytes


class Store(PreviewStore):
    client = SimpleNamespace(get_bucket_versioning="versioning")

    def __init__(self):
        super().__init__()
        self.sources, self.artifacts = {}, {}
        self.lost_ack = False
        self.versioning = {}
        self.after_artifact_read = None

    async def presign_upload(self, ref, size, checksum, ttl):
        grant = await super().presign_upload(ref, size, checksum, ttl)
        self.sources[ref.key] = (self.body, self.info)
        return grant

    async def inspect_upload(self, ref):
        if ref.key in self.sources:
            return self.sources[ref.key][1]
        if ref.key in self.artifacts:
            return ObjectInfo(
                len(self.artifacts[ref.key]),
                "application/octet-stream",
                '"artifact"',
                datetime.now(UTC),
            )
        raise ObjectNotFoundError("missing")

    async def read_for_processing(self, ref, maximum):
        if self.after_read:
            await self.after_read()
        return self.sources[ref.key][0]

    async def put_small(self, ref, content):
        if ref.key in self.artifacts:
            raise ObjectConflictError("immutable")
        self.artifacts[ref.key] = content
        if self.lost_ack:
            raise StorageError("private-lost-ack")

    async def read_small(self, ref, maximum):
        if self.after_artifact_read:
            await self.after_artifact_read()
        if ref.key not in self.artifacts:
            raise ObjectNotFoundError("missing")
        return self.artifacts[ref.key]

    async def delete(self, ref):
        self.artifacts.pop(ref.key, None)

    async def call(self, operation):
        assert operation == "versioning"
        return self.versioning

    async def close(self):
        pass


@pytest_asyncio.fixture
async def storage(monkeypatch):
    store = Store()
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "cv-preview-jobs")

    async def dependency():
        yield store

    async def renderer(data, page):
        return PreviewContent.model_validate(render(data, page))

    monkeypatch.setattr("app.services.previews.isolated_render", renderer)
    app.dependency_overrides[get_upload_storage] = dependency
    yield store
    app.dependency_overrides.pop(get_upload_storage, None)


async def enqueue(client, owner, file_id, **kwargs):
    response = await client.post(
        f"/api/v1/files/{file_id}/preview-jobs",
        headers=bearer(owner),
        json={"request_id": str(uuid4()), **kwargs},
    )
    assert response.status_code == 202, response.text
    return response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"<script>inert text</script>", image_bytes()])
async def test_queued_bytes_stay_in_storage_not_metadata_and_result_is_authorized(
    client, db_factory, storage, body
):
    owner = await register_user(client)
    storage.body = body
    file_id = await complete(client, owner, storage)
    job = await enqueue(client, owner, file_id)
    assert not storage.artifacts
    async with db_factory() as db:
        assert await PreviewJobService(db, storage).process_next() == "ready"
        row = await db.get(PreviewJob, UUID(job["id"]))
        assert "text" not in row.metadata_json and "image_base64" not in row.metadata_json
    response = await client.get(
        f"/api/v1/files/{file_id}/preview-jobs/{job['id']}", headers=bearer(owner)
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    result = response.json()["preview"]
    assert result["scan_status"] == "unscanned"
    assert result["kind"] == ("text" if body.startswith(b"<") else "image")
    assert "http" not in str(result)


@pytest.mark.asyncio
async def test_job_idempotency_private_requester_cancel_and_claim_fencing(
    client, db_factory, storage
):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    file_id = await complete(client, owner, storage)
    request_id = str(uuid4())
    job = await enqueue(client, owner, file_id, request_id=request_id)
    assert (await enqueue(client, owner, file_id, request_id=request_id))["id"] == job["id"]
    path = f"/api/v1/files/{file_id}/preview-jobs/{job['id']}"
    assert (await client.get(path, headers=bearer(member))).status_code == 404
    assert (await client.delete(path, headers=bearer(member))).status_code == 404
    async with db_factory() as db:
        service = PreviewJobService(db, storage)
        old = await service.claim()
        await db.rollback()
        assert (await client.delete(path, headers=bearer(owner))).json()["state"] == "cancelled"
        assert await service.process_next(old) == "superseded"
    assert not storage.artifacts


@pytest.mark.asyncio
async def test_current_generation_change_cancels_job_but_explicit_history_survives(
    client, db_factory, storage
):
    owner = await register_user(client)
    file_id = await complete(client, owner, storage)
    current = await enqueue(client, owner, file_id)
    async with db_factory() as db:
        version = await db.scalar(select(FileVersion).where(FileVersion.file_id == UUID(file_id)))
        version_id = version.id
    history = await enqueue(client, owner, file_id, version_id=str(version_id))
    async with db_factory() as db:
        file = await db.get(File, UUID(file_id))
        file.version_generation += 1
        await db.commit()
    async with db_factory() as db:
        service = PreviewJobService(db, storage)
        for _ in range(2):
            await service.process_next()
        assert (await db.get(PreviewJob, UUID(current["id"]))).state == "cancelled"
        assert (await db.get(PreviewJob, UUID(history["id"]))).state == "ready"


@pytest.mark.asyncio
async def test_revocation_during_render_and_artifact_read_never_publishes(
    client, db_factory, storage
):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    file_id = await complete(client, owner, storage)
    await enqueue(client, member, file_id)

    async def revoke():
        async with db_factory() as db:
            membership = await db.scalar(
                select(Membership).where(Membership.user_id == UUID(member["user"]["id"]))
            )
            membership.revoked_at = datetime.now(UTC)
            await db.commit()

    storage.after_read = revoke
    async with db_factory() as db:
        assert await PreviewJobService(db, storage).process_next() == "cancelled"
    assert not storage.artifacts
    # A separate ready owner result also rechecks current membership after object read.
    storage.after_read = None
    ready = await enqueue(client, owner, file_id)
    async with db_factory() as db:
        assert await PreviewJobService(db, storage).process_next() == "ready"

    async def revoke_owner():
        async with db_factory() as db:
            membership = await db.scalar(
                select(Membership).where(Membership.user_id == UUID(owner["user"]["id"]))
            )
            membership.revoked_at = datetime.now(UTC)
            await db.commit()

    storage.after_artifact_read = revoke_owner
    response = await client.get(
        f"/api/v1/files/{file_id}/preview-jobs/{ready['id']}", headers=bearer(owner)
    )
    assert response.status_code == 403 and "preview" not in response.json()


@pytest.mark.asyncio
async def test_lost_write_ack_retries_same_immutable_artifact_and_cleanup_rechecks_late_writes(
    client, db_factory, storage
):
    owner = await register_user(client)
    file_id = await complete(client, owner, storage)
    job = await enqueue(client, owner, file_id)
    storage.lost_ack = True
    async with db_factory() as db:
        service = PreviewJobService(db, storage)
        assert await service.process_next() == "queued"
        row = await db.get(PreviewJob, UUID(job["id"]))
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
        storage.lost_ack = False
        assert await service.process_next() == "ready"
        row = await db.get(PreviewJob, UUID(job["id"]))
        cleanup = row.cleanup_after.replace(tzinfo=UTC) + timedelta(seconds=1)
        artifact_key = service.ref(row).key
        await db.rollback()
        assert await service.cleanup_one(cleanup) == "cleaned_reference_retained"
        storage.artifacts[artifact_key] = b"late write"
        assert (
            await service.cleanup_one(cleanup + timedelta(seconds=1))
            == "cleaned_reference_retained"
        )
        assert not storage.artifacts and await db.get(PreviewJob, UUID(job["id"]))


@pytest.mark.asyncio
async def test_claim_duplicate_recovery_and_exhaustion(db_factory, storage):
    now = datetime.now(UTC)
    from app.services.background_jobs import storage_namespace

    async with db_factory() as db:
        db.add(
            PreviewJob(
                tenant_id=uuid4(),
                file_id=uuid4(),
                version_id=uuid4(),
                requested_by=uuid4(),
                request_id=uuid4(),
                generation=0,
                page=0,
                storage_bucket=settings.S3_BUCKET_NAME,
                namespace=storage_namespace(),
                next_attempt_at=now,
                expires_at=now + timedelta(hours=1),
                cleanup_after=now + timedelta(hours=2),
            )
        )
        await db.commit()

    async def claim(time):
        async with db_factory() as db:
            return await PreviewJobService(db, storage).claim(time)

    claims = await asyncio.gather(claim(now), claim(now))
    assert sum(item is not None for item in claims) == 1
    first = next(item for item in claims if item)
    second = await claim(now + timedelta(seconds=400))
    third = await claim(now + timedelta(seconds=800))
    assert first.lease_id != second.lease_id != third.lease_id
    assert await claim(now + timedelta(seconds=1200)) is None
    async with db_factory() as db:
        assert (await db.get(PreviewJob, first.id)).state == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["prune", "trash", "corrupt"])
async def test_ready_result_rechecks_lifecycle_and_integrity(client, db_factory, storage, change):
    from tests.api.test_trash import trash

    owner = await register_user(client)
    file_id = await complete(client, owner, storage)
    job = await enqueue(client, owner, file_id)
    async with db_factory() as db:
        assert await PreviewJobService(db, storage).process_next() == "ready"
    if change == "prune":
        async with db_factory() as db:
            version = await db.scalar(
                select(FileVersion).where(FileVersion.file_id == UUID(file_id))
            )
            version.prune_requested_at = datetime.now(UTC)
            version.prune_not_before = datetime.now(UTC) + timedelta(minutes=15)
            await db.commit()
    elif change == "trash":
        await trash(client, owner, "files", file_id)
    else:
        key = next(iter(storage.artifacts))
        storage.artifacts[key] = b"corrupt result"
    response = await client.get(
        f"/api/v1/files/{file_id}/preview-jobs/{job['id']}", headers=bearer(owner)
    )
    assert response.status_code in (404, 409)
    assert "preview" not in response.json()


@pytest.mark.asyncio
async def test_cancel_during_native_render_fences_publication(client, db_factory, storage):
    owner = await register_user(client)
    storage.body = image_bytes()
    file_id = await complete(client, owner, storage)
    job = await enqueue(client, owner, file_id)

    async def renderer(data, page):
        response = await client.delete(
            f"/api/v1/files/{file_id}/preview-jobs/{job['id']}", headers=bearer(owner)
        )
        assert response.status_code == 200
        return PreviewContent.model_validate(render(data, page))

    async with db_factory() as db:
        assert await PreviewJobService(db, storage, renderer).process_next() == "superseded"
    assert not storage.artifacts


@pytest.mark.asyncio
async def test_versioned_cleanup_degrades_without_dropping_refs(client, db_factory, storage):
    from app.services.job_backlog import backlog

    owner = await register_user(client)
    file_id = await complete(client, owner, storage)
    job = await enqueue(client, owner, file_id)
    async with db_factory() as db:
        service = PreviewJobService(db, storage)
        assert await service.process_next() == "ready"
        row = await db.get(PreviewJob, UUID(job["id"]))
        later = row.cleanup_after.replace(tzinfo=UTC) + timedelta(seconds=1)
        await db.rollback()
        storage.versioning = {"Status": "Enabled"}
        assert await service.cleanup_one(later) == "deferred"
        assert storage.artifacts
        assert (await backlog(db_factory, "previews", later))["deferred_preview_cleanup"][
            "count"
        ] == 1
        storage.versioning = {}
        assert (
            await service.cleanup_one(later + timedelta(seconds=1)) == "cleaned_reference_retained"
        )
    assert not storage.artifacts


@pytest.mark.asyncio
async def test_registered_preview_worker_uses_durable_job_and_health_row(
    client, db_factory, storage, monkeypatch
):
    from app.jobs import preview_queue, tasks
    from app.models import BackgroundJob

    owner = await register_user(client)
    file_id = await complete(client, owner, storage)
    job = await enqueue(client, owner, file_id)
    monkeypatch.setattr(
        settings, "DATABASE_URL", db_factory.kw["bind"].url.render_as_string(hide_password=False)
    )
    monkeypatch.setattr(preview_queue, "S3ObjectStorage", lambda config, tenant: storage)
    assert await tasks.run_job("previews") == "completed"
    async with db_factory() as db:
        assert (await db.get(PreviewJob, UUID(job["id"]))).state == "ready"
        heartbeat = await db.get(BackgroundJob, "previews")
        assert heartbeat.runs == 1 and heartbeat.last_success_at and heartbeat.lease_id is None
