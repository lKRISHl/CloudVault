"""Real Redis restart and prefork crash checks against the owned disposable stack only."""

import json
import time
from uuid import uuid4

from phase16_stack import MANIFEST, ROOT, compose


def main():
    manifest = json.loads(MANIFEST.read_text())
    if manifest["root"] != str(ROOT):
        raise ValueError("Acceptance workspace changed")
    project = manifest["project"]

    def run(*args):
        return compose(project, *args, capture_output=True, text=True).stdout.strip()

    def backend(code):
        return run("exec", "-T", "backend", "python", "-c", code)

    def snapshot():
        value = run(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "cloudvault",
            "-d",
            "phase16_acceptance",
            "-Atc",
            "SELECT row_to_json(x) FROM (SELECT runs,lease_id,lease_expires_at,"
            "last_success_at,cursor FROM background_jobs WHERE name='storage') x",
        )
        return json.loads(value)

    def wait_for(check, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = check()
            if value:
                return value
            time.sleep(1)
        raise RuntimeError("Owned queue recovery deadline exceeded")

    paused = False
    workers = ("email-worker", "preview-worker", "upload-cleanup")
    try:
        # A prior interrupted run can leave a valid durable lease on preserved volumes.
        # Let the running scheduler reclaim it normally before beginning a new scenario.
        wait_for(lambda: snapshot()["lease_id"] is None, 310)
        run("stop", "job-scheduler", *workers)
        baseline = snapshot()
        backend(
            "from app.jobs.tasks import storage_maintenance; storage_maintenance.delay(); storage_maintenance.delay()"
        )
        count = int(
            run("exec", "-T", "redis", "redis-cli", "LLEN", "cloudvault:storage")
        )
        assert count >= 2, "Maintenance hints did not reach Redis"
        time.sleep(
            2
        )  # Allow the configured every-second AOF fsync before orderly restart.
        run("restart", "redis")
        wait_for(lambda: run("exec", "-T", "redis", "redis-cli", "PING") == "PONG", 20)
        assert (
            int(run("exec", "-T", "redis", "redis-cli", "LLEN", "cloudvault:storage"))
            == count
        )
        print("Redis AOF preserved queued hints across broker restart", flush=True)
        run("up", "-d", "--no-deps", "upload-cleanup")
        wait_for(
            lambda: (
                snapshot()["runs"] >= baseline["runs"] + 2
                and not snapshot()["lease_id"]
            ),
            40,
        )
        run("stop", "upload-cleanup")
        before = snapshot()
        fixture_tag = uuid4().hex + "0" * 32
        backend(f'''
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from app.core.database import async_session_maker
from app.core.config import settings
from app.models import Tenant, UploadIntent
from app.storage.s3 import S3ObjectStorage
from app.storage.base import ObjectRef
async def seed():
    async with async_session_maker() as db:
        for index in range(2):
            tenant = Tenant(name="Owned queue backlog", slug="queue-backlog-" + uuid4().hex)
            db.add(tenant)
            await db.flush()
            store = S3ObjectStorage(settings, tenant.id)
            try:
                for number in range(6):
                    record = UploadIntent(file_id=uuid4(), tenant_id=tenant.id,
                        object_id=uuid4(), created_by=uuid4(), request_id=uuid4(),
                        storage_bucket=settings.S3_BUCKET_NAME, fingerprint="{fixture_tag}",
                        expires_at=datetime.now(UTC)-timedelta(hours=3), scope_recorded=False)
                    db.add(record)
                    await store.put_small(ObjectRef(record.tenant_id, record.file_id, record.object_id), b"owned expired fixture")
            finally:
                await store.close()
        await db.commit()
asyncio.run(seed())
''')
        run("pause", "minio")
        paused = True
        run("up", "-d", "--no-deps", "upload-cleanup")
        backend(
            "from app.jobs.tasks import storage_maintenance; storage_maintenance.delay()"
        )
        active = wait_for(
            lambda: (
                s
                if (s := snapshot())["lease_id"]
                and s["cursor"]["next_stage"] != before["cursor"]["next_stage"]
                else None
            ),
            30,
        )
        assert active["cursor"]["next_stage"] != before["cursor"]["next_stage"]
        # Only the owned worker's prefork child is killed; its PID 1 supervisor remains.
        killed = run(
            "exec",
            "-T",
            "upload-cleanup",
            "python",
            "-c",
            "import os,signal; from pathlib import Path; "
            "children=[int(p.name) for p in Path('/proc').iterdir() if p.name.isdigit() "
            "and p.name not in ('1',str(os.getpid())) and "
            "any(line=='PPid:\\t1' for line in (p/'status').read_text().splitlines())]; "
            "assert len(children)==1,children; os.kill(children[0],signal.SIGKILL); print('prefork child killed')",
        )
        assert killed == "prefork child killed"
        time.sleep(2)
        retained = snapshot()
        assert retained["lease_id"] == active["lease_id"]
        assert retained["cursor"] == active["cursor"]
        print(
            "Killed actual prefork child during provider I/O; committed rotation and lease survived",
            flush=True,
        )
        run("unpause", "minio")
        paused = False
        run("up", "-d", "--no-deps", "job-scheduler", *workers)
        # Actual 240-second lease window. No database timestamp manipulation.
        recovered = wait_for(
            lambda: (
                s
                if (s := snapshot())["runs"] > active["runs"] and s["lease_id"] is None
                else None
            ),
            280,
        )
        assert recovered["last_success_at"] > active["last_success_at"]
        assert recovered["cursor"]["next_stage"] != active["cursor"]["next_stage"]
        print(
            "Real-clock lease expiry recovered interrupted work without losing the stage checkpoint",
            flush=True,
        )
        wait_for(
            lambda: all(
                entry.get("success_at", "") > active["last_success_at"]
                for entry in snapshot()["cursor"]["stages"].values()
            ),
            65,
        )
        print("All six stages made progress after crash recovery", flush=True)

        def remaining():
            return int(
                run(
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-U",
                    "cloudvault",
                    "-d",
                    "phase16_acceptance",
                    "-Atc",
                    "SELECT count(*) FROM upload_intents "
                    f"WHERE fingerprint='{fixture_tag}' AND checked_at IS NULL",
                )
            )

        wait_for(lambda: remaining() == 0, 110)
        backend(f'''
import asyncio
from sqlalchemy import select
from app.core.database import async_session_maker
from app.core.config import settings
from app.models import UploadIntent
from app.storage.s3 import S3ObjectStorage
from app.storage.base import ObjectRef, ObjectNotFoundError
async def verify():
    async with async_session_maker() as db:
        rows = list(await db.scalars(select(UploadIntent).where(UploadIntent.fingerprint=="{fixture_tag}")))
        assert len(rows)==12 and len(set(row.tenant_id for row in rows))==2
        for row in rows:
            store = S3ObjectStorage(settings, row.tenant_id)
            try:
                try:
                    await store.head(ObjectRef(row.tenant_id,row.file_id,row.object_id))
                except ObjectNotFoundError:
                    pass
                else:
                    raise AssertionError("Owned expired bytes remain")
            finally:
                await store.close()
asyncio.run(verify())
''')
        print(
            "Real worker drained 12 expired references across two tenants in bounded batches; exact bytes absent",
            flush=True,
        )
    finally:
        if paused:
            run("unpause", "minio")
        run("up", "-d", "--no-deps", "job-scheduler", *workers)


if __name__ == "__main__":
    main()
