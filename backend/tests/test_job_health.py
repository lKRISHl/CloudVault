from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.jobs import check_jobs, cleanup_trash, cleanup_uploads
from app.models import EmailOutbox
from app.services.job_backlog import backlog
from app.storage.base import StorageError


@pytest.mark.asyncio
async def test_email_backlog_excludes_sent_expired_leased_and_delayed(db_factory):
    now = datetime.now(UTC)
    base = dict(
        purpose="verify",
        recipient_key="private-recipient-key",
        encrypted_payload="private-payload",
        next_attempt_at=now - timedelta(minutes=3),
        expires_at=now + timedelta(hours=1),
    )
    async with db_factory() as db:
        for changes in (
            {},
            {"sent_at": now},
            {"expires_at": now},
            {"lease_until": now + timedelta(minutes=1)},
            {"next_attempt_at": now + timedelta(minutes=1)},
            {"encrypted_payload": None},
        ):
            db.add(EmailOutbox(**{**base, **changes}))
        await db.commit()
    result = await backlog(db_factory, "email", now)
    assert result["due_deliveries"] == {"count": 1, "oldest_age_seconds": 180}
    assert result["retrying_deliveries"]["count"] == 0
    assert "private" not in str(result)
    storage = await backlog(db_factory, "storage", now)
    assert all(item["count"] == 0 for item in storage.values())


@pytest.mark.asyncio
async def test_email_health_exposes_retrying_work_even_before_retry_is_due(db_factory, monkeypatch):
    from app.services.background_jobs import BackgroundJobService

    now = datetime.now(UTC)
    monkeypatch.setattr(
        settings, "DATABASE_URL", db_factory.kw["bind"].url.render_as_string(hide_password=False)
    )
    async with db_factory() as db:
        db.add(
            EmailOutbox(
                purpose="verify",
                recipient_key="private-recipient",
                encrypted_payload="private",
                next_attempt_at=now + timedelta(minutes=2),
                expires_at=now + timedelta(hours=1),
                error_code="smtp_unavailable",
                created_at=now - timedelta(minutes=4),
            )
        )
        await db.commit()

    async def healthy_invocation(cursor):
        return None

    await BackgroundJobService(db_factory).run("email", healthy_invocation)
    result = (await check_jobs.inspect(["email"]))[0]
    assert result["state"] == "degraded"
    assert result["backlog"]["due_deliveries"]["count"] == 0
    assert result["backlog"]["retrying_deliveries"]["count"] == 1
    assert result["backlog"]["retrying_deliveries"]["oldest_age_seconds"] >= 240
    assert "private" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "versioning,failed,expected",
    [
        ({}, False, "ok"),
        ({"Status": "Enabled"}, False, "versioning_refused"),
        ({"Status": "Suspended"}, False, "versioning_refused"),
        ({}, True, "unavailable"),
    ],
)
async def test_storage_health_probes_without_writing_and_redacts_errors(
    monkeypatch,
    versioning,
    failed,
    expected,
):
    seen = []

    class Storage:
        client = SimpleNamespace(get_bucket_versioning="versioning")

        def __init__(self, *args):
            pass

        async def check_bucket(self):
            seen.append("head")
            if failed:
                raise StorageError("secret endpoint signed URL")

        async def call(self, operation):
            assert operation == "versioning"
            seen.append(operation)
            return versioning

        async def close(self):
            seen.append("close")

    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "test-only-bucket")
    monkeypatch.setattr(check_jobs, "S3ObjectStorage", Storage)
    assert await check_jobs.storage_dependency() == expected
    assert seen == (["head", "close"] if failed else ["head", "versioning", "close"])


@pytest.mark.asyncio
async def test_stage_routes_only_selected_work_and_retains_inventory_marker(
    db_factory, monkeypatch
):
    seen = []

    class Inventory:
        client = SimpleNamespace(get_bucket_versioning="versioning")

        def __init__(self, *args):
            pass

        async def call(self, operation):
            assert operation == "versioning"
            return {}

        async def close(self):
            pass

    async def orphan(inventory, factory, marker, now, *, page_size, report):
        seen.append(("orphans", page_size))
        return ("next-key", "next-upload")

    async def trash(factory, *, limit, report):
        seen.append(("trash", limit))

    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "test-only-bucket")
    monkeypatch.setattr(cleanup_uploads, "S3ObjectStorage", Inventory)
    monkeypatch.setattr(cleanup_uploads, "sweep_orphans", orphan)
    monkeypatch.setattr(cleanup_trash, "tick", trash)
    marker = ("key", "upload")
    for stage in ("uploads", "intents", "policies", "versions"):
        assert await cleanup_uploads.tick(db_factory, marker, stage=stage, batch_size=2) == marker
    assert seen == []
    assert await cleanup_uploads.tick(db_factory, marker, stage="trash", batch_size=2) == marker
    assert await cleanup_uploads.tick(db_factory, marker, stage="orphans", batch_size=2) == (
        "next-key",
        "next-upload",
    )
    assert seen == [("trash", 2), ("orphans", 2)]
    for options in ({"stage": "unknown"}, {"batch_size": 0}, {"batch_size": 51}):
        with pytest.raises(ValueError):
            await cleanup_uploads.tick(db_factory, **options)


@pytest.mark.asyncio
async def test_oversized_inventory_page_has_no_cleanup_side_effects(db_factory):
    class Inventory:
        client = SimpleNamespace(list_multipart_uploads="list")

        async def call(self, operation, **kwargs):
            assert kwargs["MaxUploads"] == 1
            return {"Uploads": [{}, {}]}

    with pytest.raises(StorageError, match="page limit"):
        await cleanup_uploads.sweep_orphans(Inventory(), db_factory, page_size=1)
