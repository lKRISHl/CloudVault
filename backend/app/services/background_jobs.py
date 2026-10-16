"""Durable maintenance leases and checkpoints, independent of broker delivery guarantees."""

import hashlib
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.config import settings
from app.models import BackgroundJob
from app.services.uploads import utc

JOBS = frozenset(("email", "storage", "previews", "scans"))
STORAGE_STAGES = ("uploads", "intents", "orphans", "policies", "versions", "trash", "quotas")


def storage_state(cursor):
    if not cursor or cursor.get("namespace") != storage_namespace():
        return {"namespace": storage_namespace(), "marker": None, "next_stage": 0, "stages": {}}
    state = deepcopy(cursor)
    read_marker(state)
    position = state.setdefault("next_stage", 0)
    if type(position) is not int or not 0 <= position < len(STORAGE_STAGES):
        raise ValueError("Invalid stage checkpoint")
    stages = state.setdefault("stages", {})
    if not isinstance(stages, dict) or any(key not in STORAGE_STAGES for key in stages):
        raise ValueError("Invalid stage state")
    return state


def completed_stage(cursor, result=None, *, success, now=None):
    now = now or datetime.now(UTC)
    state = deepcopy(cursor)
    stage = state.pop("_stage")
    if success:
        if not isinstance(result, dict) or result.get("namespace") != state["namespace"]:
            raise ValueError("Invalid stage result")
        marker = read_marker(result)
        state["marker"] = list(marker) if marker else None
        for key in ("orphan_cycle_deferred", "last_cycle_deferred"):
            value = result.get(key, state.get(key, 0))
            if type(value) is not int or value < 0:
                raise ValueError("Invalid inventory outcome")
            state[key] = value
    entry = state["stages"][stage]
    entry["finished_at"] = now.isoformat()
    if success:
        report = result.get("_report", {})
        if not isinstance(report, dict) or any(
            key not in ("inspected", "deferred") or type(value) is not int or value < 0
            for key, value in report.items()
        ):
            raise ValueError("Invalid stage report")
        entry.update(success_at=now.isoformat(), failures=0, last_batch=report)
    else:
        entry.update(error_at=now.isoformat(), failures=entry.get("failures", 0) + 1)
    return state


def storage_namespace():
    value = "|".join(
        (settings.S3_ENDPOINT or "aws", settings.S3_REGION, settings.S3_BUCKET_NAME or "")
    )
    return hashlib.sha256(value.encode()).hexdigest()


def read_marker(cursor):
    if not cursor or cursor.get("namespace") != storage_namespace():
        return None
    marker = cursor.get("marker")
    if marker is None:
        return None
    if (
        not isinstance(marker, list)
        or len(marker) != 2
        or any(not isinstance(value, str) or len(value) > 4096 for value in marker)
    ):
        raise ValueError("Invalid maintenance checkpoint")
    return tuple(marker)


def stage_health(cursor, now):
    state = storage_state(cursor)
    maximum_age = max(
        600,
        settings.UPLOAD_CLEANUP_INTERVAL_SECONDS * len(STORAGE_STAGES) + settings.JOB_LEASE_SECONDS,
    )
    results = {}
    for name in STORAGE_STAGES:
        entry = state["stages"].get(name, {})
        success = entry.get("success_at")
        age = (now - datetime.fromisoformat(success)).total_seconds() if success else None
        status = "never_run" if age is None else "stale" if age > maximum_age else "ok"
        if entry.get("failures", 0):
            status = "failed"
        if entry.get("started_at", "") > entry.get("finished_at", ""):
            started = datetime.fromisoformat(entry["started_at"])
            if (now - started).total_seconds() > settings.JOB_LEASE_SECONDS:
                status = "interrupted"
        batch = entry.get("last_batch", {})
        if status == "ok" and (
            batch.get("deferred", 0)
            or name == "orphans"
            and (state.get("orphan_cycle_deferred", 0) or state.get("last_cycle_deferred", 0))
        ):
            status = "deferred"
        results[name] = {"state": status, "last_success_age_seconds": age, "last_batch": batch}
    return results


class BackgroundJobService:
    def __init__(self, factory):
        self.factory = factory

    async def reserve_preview_turn(self, token, cursor):
        turn = (cursor or {}).get("next_turn", "render")
        if turn not in ("render", "cleanup"):
            raise ValueError("Invalid preview checkpoint")
        state = {"next_turn": "cleanup" if turn == "render" else "render"}
        async with self.factory() as db:
            result = await db.execute(
                update(BackgroundJob)
                .where(
                    BackgroundJob.name == "previews",
                    BackgroundJob.lease_id == token,
                    BackgroundJob.lease_expires_at > datetime.now(UTC),
                )
                .values(cursor=state)
            )
            await db.commit()
            if result.rowcount != 1:
                raise RuntimeError("Preview lease expired or was replaced")
        return {**state, "turn": turn}

    async def reserve_stage(self, token, cursor, now=None):
        now = now or datetime.now(UTC)
        state = storage_state(cursor)
        previous = state.get("active_stage")
        old = state["stages"].get(previous, {})
        if old.get("started_at") and old.get("finished_at", "") < old["started_at"]:
            old.update(
                error_at=now.isoformat(),
                finished_at=now.isoformat(),
                failures=old.get("failures", 0) + 1,
            )
        stage = STORAGE_STAGES[state["next_stage"]]
        state["next_stage"] = (state["next_stage"] + 1) % len(STORAGE_STAGES)
        state["active_stage"] = stage
        entry = state["stages"].setdefault(stage, {})
        entry.update(started_at=now.isoformat(), attempts=entry.get("attempts", 0) + 1)
        async with self.factory() as db:
            result = await db.execute(
                update(BackgroundJob)
                .where(
                    BackgroundJob.name == "storage",
                    BackgroundJob.lease_id == token,
                    BackgroundJob.lease_expires_at > now,
                )
                .values(cursor=state)
            )
            await db.commit()
            if result.rowcount != 1:
                raise RuntimeError("Storage lease expired or was replaced")
        return {**deepcopy(state), "_stage": stage}

    async def claim(self, name, now=None):
        if name not in JOBS:
            raise ValueError("Unknown background job")
        now = now or datetime.now(UTC)
        token = uuid4()
        async with self.factory() as db:
            insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
            await db.execute(
                insert(BackgroundJob)
                .values(name=name, runs=0, failures=0)
                .on_conflict_do_nothing(index_elements=["name"])
            )
            result = await db.execute(
                update(BackgroundJob)
                .where(
                    BackgroundJob.name == name,
                    or_(
                        BackgroundJob.lease_expires_at.is_(None),
                        BackgroundJob.lease_expires_at <= now,
                    ),
                )
                .values(
                    lease_id=token,
                    lease_expires_at=now + timedelta(seconds=settings.JOB_LEASE_SECONDS),
                    started_at=now,
                    runs=BackgroundJob.runs + 1,
                )
                .returning(BackgroundJob.cursor)
            )
            row = result.first()
            await db.commit()
        return (token, row[0]) if row is not None else None

    async def finish(self, name, token, *, success, cursor=None, now=None):
        now = now or datetime.now(UTC)
        values = {"lease_id": None, "lease_expires_at": None, "finished_at": now}
        if success:
            values.update(last_success_at=now, failures=0, cursor=cursor)
        else:
            values.update(last_error_at=now, failures=BackgroundJob.failures + 1)
            if cursor is not None:
                values["cursor"] = cursor
        async with self.factory() as db:
            result = await db.execute(
                update(BackgroundJob)
                .where(
                    BackgroundJob.name == name,
                    BackgroundJob.lease_id == token,
                )
                .values(**values)
            )
            await db.commit()
            return result.rowcount == 1

    async def run(self, name, handler):
        claim = await self.claim(name)
        if claim is None:
            return "busy"
        token, cursor = claim
        try:
            if name == "storage":
                cursor = await self.reserve_stage(token, cursor)
            elif name == "previews":
                cursor = await self.reserve_preview_turn(token, cursor)
            result = await handler(cursor)
            if name == "storage":
                result = completed_stage(cursor, result, success=True)
        except Exception:
            failure_state = (
                completed_stage(cursor, success=False)
                if name == "storage" and isinstance(cursor, dict) and "_stage" in cursor
                else None
            )
            await self.finish(name, token, success=False, cursor=failure_state)
            raise
        if not await self.finish(name, token, success=True, cursor=result):
            raise RuntimeError("Background job lease was replaced")
        return "completed"

    async def health(self, name, now=None):
        if name not in JOBS:
            raise ValueError("Unknown background job")
        now = now or datetime.now(UTC)
        maximum_age = (
            60
            if name in ("email", "previews", "scans")
            else max(300, settings.UPLOAD_CLEANUP_INTERVAL_SECONDS * 3)
        )
        async with self.factory() as db:
            row = await db.scalar(select(BackgroundJob).where(BackgroundJob.name == name))
            if row is None:
                return {
                    "name": name,
                    "state": "never_run",
                    "running": False,
                    "runs": 0,
                    "failures": 0,
                }
            age = (now - utc(row.last_success_at)).total_seconds() if row.last_success_at else None
            state = "never_succeeded" if age is None else "ok" if age <= maximum_age else "stale"
            if row.last_error_at and (
                not row.last_success_at or utc(row.last_error_at) > utc(row.last_success_at)
            ):
                state = "failed"
            result = {
                "name": name,
                "state": state,
                "running": bool(
                    row.lease_id and row.lease_expires_at and utc(row.lease_expires_at) > now
                ),
                "runs": row.runs,
                "failures": row.failures,
                "last_success_age_seconds": age,
            }
            if name == "storage":
                result["stages"] = stage_health(row.cursor, now)
                states = {entry["state"] for entry in result["stages"].values()}
                if state == "ok" and states != {"ok"}:
                    result["state"] = "warming_up" if states <= {"ok", "never_run"} else "degraded"
            return result
