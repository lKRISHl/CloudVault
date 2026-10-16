import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import BackgroundJob
from app.services.background_jobs import BackgroundJobService, read_marker, storage_namespace


@pytest.mark.asyncio
async def test_lease_duplicate_delivery_recovery_and_fencing(db_factory):
    service = BackgroundJobService(db_factory)
    now = datetime.now(UTC)
    claims = await asyncio.gather(service.claim("storage", now), service.claim("storage", now))
    assert sum(item is not None for item in claims) == 1
    first = next(item[0] for item in claims if item)
    assert await service.claim("storage", now + timedelta(seconds=10)) is None
    second, _ = await service.claim("storage", now + timedelta(seconds=1000))
    assert not await service.finish("storage", first, success=True, cursor={"obsolete": True})
    cursor = {"namespace": storage_namespace(), "marker": ["key", "upload"]}
    assert await service.finish("storage", second, success=True, cursor=cursor)
    async with db_factory() as db:
        state = await db.get(BackgroundJob, "storage")
        assert state.cursor == cursor and state.runs == 2 and state.lease_id is None


@pytest.mark.asyncio
async def test_failed_job_preserves_checkpoint_and_health_recovers(db_factory):
    service = BackgroundJobService(db_factory)
    assert (await service.health("email"))["state"] == "never_run"
    cursor = {"namespace": storage_namespace(), "marker": ["key", "upload"]}

    async def success(previous):
        return cursor

    await service.run("email", success)
    assert (await service.health("email"))["state"] == "ok"

    async def failed(previous):
        assert previous == cursor
        raise RuntimeError("sensitive provider error")

    with pytest.raises(RuntimeError):
        await service.run("email", failed)
    health = await service.health("email")
    assert health["state"] == "failed" and health["failures"] == 1
    assert "sensitive" not in str(health) and "cursor" not in health
    async with db_factory() as db:
        assert (await db.get(BackgroundJob, "email")).cursor == cursor
    await service.run("email", success)
    assert (await service.health("email"))["state"] == "ok"
    assert (await service.health("email", datetime.now(UTC) + timedelta(hours=1)))[
        "state"
    ] == "stale"


@pytest.mark.asyncio
async def test_busy_job_never_calls_handler_and_unknown_job_has_no_state(db_factory):
    service = BackgroundJobService(db_factory)
    await service.claim("email")

    async def forbidden(cursor):
        pytest.fail("Duplicate handler must not run")

    assert await service.run("email", forbidden) == "busy"
    with pytest.raises(ValueError):
        await service.run("arbitrary-user-task", forbidden)
    async with db_factory() as db:
        assert list(await db.scalars(select(BackgroundJob.name))) == ["email"]


def test_cursor_resets_on_provider_change_and_rejects_invalid_shape(monkeypatch):
    from app.core.config import settings

    cursor = {"namespace": storage_namespace(), "marker": ["key", "upload"]}
    assert read_marker(cursor) == ("key", "upload")
    with pytest.raises(ValueError):
        read_marker({**cursor, "marker": ["wrong"]})
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "different-bucket")
    assert read_marker(cursor) is None


def test_celery_queues_are_json_only_late_ack_and_have_no_result_backend():
    from app.jobs.celery_app import celery_app

    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.task_acks_late and celery_app.conf.task_reject_on_worker_lost
    assert celery_app.conf.task_ignore_result and not celery_app.conf.result_backend
    assert (
        celery_app.conf.task_time_limit
        < 240
        < celery_app.conf.broker_transport_options["visibility_timeout"]
    )
    assert not celery_app.conf.worker_enable_remote_control
    assert set(celery_app.conf.beat_schedule) == {"email", "storage", "previews"}
    assert all(
        not item.get("args") and not item.get("kwargs")
        for item in celery_app.conf.beat_schedule.values()
    )


def test_registered_task_dispatch_and_retry_do_not_expose_exception(monkeypatch):
    from app.jobs import tasks

    seen = []

    async def run(name):
        seen.append(name)
        return "completed"

    monkeypatch.setattr(tasks, "run_job", run)
    assert tasks.email_maintenance.apply(throw=True).result == "completed"
    assert tasks.storage_maintenance.apply(throw=True).result == "completed"
    assert tasks.preview_maintenance.apply(throw=True).result == "completed"
    assert seen == ["email", "storage", "previews"]

    async def failed(name):
        raise RuntimeError("secret recipient and signed URL")

    monkeypatch.setattr(tasks, "run_job", failed)
    from celery.exceptions import Retry

    with pytest.raises(Retry) as error:
        tasks.email_maintenance.apply(throw=True)
    assert "secret recipient" not in str(error.value)
    assert "durable records retained" in str(error.value)
    import traceback

    assert "secret recipient" not in "".join(traceback.format_exception(error.value))


@pytest.mark.asyncio
async def test_email_task_runs_in_separate_event_loops_against_database(db_factory, monkeypatch):
    from app.core.config import settings
    from app.jobs.tasks import email_maintenance

    monkeypatch.setattr(
        settings, "DATABASE_URL", db_factory.kw["bind"].url.render_as_string(hide_password=False)
    )
    for _ in range(2):
        result = await asyncio.to_thread(lambda: email_maintenance.apply(throw=True).result)
        assert result == "completed"
    async with db_factory() as db:
        state = await db.get(BackgroundJob, "email")
        assert state.runs == 2 and state.last_success_at and not state.lease_id


@pytest.mark.asyncio
async def test_storage_task_uses_committed_inventory_marker(db_factory, monkeypatch):
    from app.core.config import settings
    from app.jobs import cleanup_uploads, tasks

    monkeypatch.setattr(
        settings, "DATABASE_URL", db_factory.kw["bind"].url.render_as_string(hide_password=False)
    )
    seen = []

    async def tick(factory, marker, *, stage, batch_size, report):
        assert batch_size == settings.STORAGE_STAGE_BATCH_SIZE
        if stage == "orphans":
            seen.append(marker)
            return ("key", "upload") if marker is None else None
        return marker

    monkeypatch.setattr(cleanup_uploads, "tick", tick)
    for _ in range(9):
        assert await tasks.run_job("storage") == "completed"
    assert seen == [None, ("key", "upload")]
    async with db_factory() as db:
        state = await db.get(BackgroundJob, "storage")
        assert state.cursor["marker"] is None
        assert set(state.cursor["stages"]) == {
            "uploads",
            "intents",
            "orphans",
            "policies",
            "versions",
            "trash",
        }


@pytest.mark.asyncio
async def test_failed_stage_rotates_and_cannot_be_masked_by_next_success(db_factory):
    service = BackgroundJobService(db_factory)
    seen = []

    async def handler(cursor):
        stage = cursor["_stage"]
        seen.append(stage)
        if stage == "uploads":
            raise RuntimeError("provider failure")
        return {**cursor, "_report": {"inspected": 1}}

    with pytest.raises(RuntimeError):
        await service.run("storage", handler)
    for _ in range(5):
        await service.run("storage", handler)
    assert seen == ["uploads", "intents", "orphans", "policies", "versions", "trash"]
    health = await service.health("storage")
    assert health["state"] == "degraded"
    assert health["stages"]["uploads"]["state"] == "failed"
    assert health["stages"]["trash"]["state"] == "ok"
    assert "provider failure" not in str(health)


@pytest.mark.asyncio
async def test_interrupted_stage_is_persisted_before_work_and_reclaimed(db_factory):
    service = BackgroundJobService(db_factory)
    now = datetime.now(UTC)
    first, cursor = await service.claim("storage", now)
    reserved = await service.reserve_stage(first, cursor, now)
    assert reserved["_stage"] == "uploads"
    later = now + timedelta(seconds=1000)
    second, cursor = await service.claim("storage", later)
    reserved = await service.reserve_stage(second, cursor, later)
    assert reserved["_stage"] == "intents"
    assert reserved["stages"]["uploads"]["failures"] == 1
    with pytest.raises(RuntimeError):
        await service.reserve_stage(first, cursor, later)
    assert not await service.finish("storage", first, success=True, cursor={})


def test_stage_health_retains_failed_orphan_cycle_until_clean_cycle(monkeypatch):
    from app.services.background_jobs import STORAGE_STAGES, stage_health, storage_state

    now = datetime.now(UTC)
    state = storage_state(None)
    state["stages"] = {stage: {"success_at": now.isoformat()} for stage in STORAGE_STAGES}
    state["last_cycle_deferred"] = 1
    assert stage_health(state, now)["orphans"]["state"] == "deferred"
    state["last_cycle_deferred"] = 0
    assert all(item["state"] == "ok" for item in stage_health(state, now).values())
    assert all(
        item["state"] == "stale" for item in stage_health(state, now + timedelta(days=1)).values()
    )
    from app.core.config import settings

    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "new-provider-bucket")
    assert all(item["state"] == "never_run" for item in stage_health(state, now).values())


@pytest.mark.asyncio
async def test_preview_turn_advances_before_failure_and_survives_interrupted_claim(db_factory):
    service = BackgroundJobService(db_factory)
    turns = []

    async def fail(cursor):
        turns.append(cursor["turn"])
        raise RuntimeError("provider unavailable")

    async def success(cursor):
        turns.append(cursor["turn"])
        return {"next_turn": cursor["next_turn"]}

    with pytest.raises(RuntimeError):
        await service.run("previews", fail)
    await service.run("previews", success)
    assert turns == ["render", "cleanup"]
    token, cursor = await service.claim("previews")
    assert (await service.reserve_preview_turn(token, cursor))["turn"] == "render"
    replacement, cursor = await service.claim(
        "previews", datetime.now(UTC) + timedelta(seconds=1000)
    )
    assert (await service.reserve_preview_turn(replacement, cursor))["turn"] == "cleanup"
    with pytest.raises(RuntimeError):
        await service.reserve_preview_turn(token, cursor)
