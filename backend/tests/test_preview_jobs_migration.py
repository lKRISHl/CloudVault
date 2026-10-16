import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4


def test_preview_migration_preserves_data_and_refuses_lost_refs_or_active_worker(tmp_path):
    path = tmp_path / "preview-jobs.db"

    def migrate(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}"},
            capture_output=True,
            text=True,
            timeout=45,
        )

    assert migrate("upgrade", "018_intent_cancellation").returncode == 0
    tenant = uuid4().hex
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO tenants(id,name,slug) VALUES(?,?,?)", (tenant, "Preserve", "preserve")
        )
    assert migrate("upgrade", "head").returncode == 0
    result = migrate("check")
    assert result.returncode == 0, result.stderr
    future = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None).isoformat(sep=" ")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO background_jobs(name,runs,failures,lease_expires_at) "
            "VALUES('previews',1,0,?)",
            (future,),
        )
    result = migrate("downgrade", "018_intent_cancellation")
    assert result.returncode != 0 and "active leases" in result.stderr
    with sqlite3.connect(path) as db:
        db.execute("UPDATE background_jobs SET lease_expires_at=NULL")
    assert migrate("downgrade", "018_intent_cancellation").returncode == 0
    assert migrate("upgrade", "head").returncode == 0
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM tenants WHERE id=?", (tenant,)).fetchone() == (
            "Preserve",
        )
        columns = (
            "id,tenant_id,file_id,version_id,requested_by,request_id,artifact_id,generation,"
            "page,state,attempts,next_attempt_at,expires_at,cleanup_after,storage_bucket,namespace"
        )
        values = [uuid4().hex for _ in range(7)] + [
            0,
            0,
            "queued",
            0,
            future,
            future,
            future,
            "private-bucket",
            "0" * 64,
        ]
        db.execute(
            f"INSERT INTO preview_jobs({columns}) VALUES({','.join('?' for _ in values)})", values
        )
    result = migrate("downgrade", "018_intent_cancellation")
    assert result.returncode != 0 and "cleanup references cannot be discarded" in result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM preview_jobs").fetchone() == (1,)
