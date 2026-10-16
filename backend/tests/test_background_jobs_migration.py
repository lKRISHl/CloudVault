import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4


def test_job_migration_preserves_tenant_and_guards_active_lease(tmp_path):
    path = tmp_path / "maintenance.db"

    def migrate(*arguments):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}"},
            capture_output=True,
            text=True,
            timeout=45,
        )

    result = migrate("upgrade", "016_library_recovery")
    assert result.returncode == 0, result.stderr
    tenant = uuid4().hex
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO tenants (id,name,slug) VALUES (?,?,?)", (tenant, "Keep", "keep"))
    result = migrate("upgrade", "head")
    assert result.returncode == 0, result.stderr
    assert migrate("check").returncode == 0
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM tenants WHERE id=?", (tenant,)).fetchone() == ("Keep",)
        db.execute(
            "INSERT INTO background_jobs (name,runs,failures,lease_expires_at) VALUES (?,?,?,?)",
            (
                "storage",
                1,
                0,
                (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None).isoformat(sep=" "),
            ),
        )
    result = migrate("downgrade", "016_library_recovery")
    assert result.returncode != 0 and "active leases" in result.stderr
    with sqlite3.connect(path) as db:
        db.execute("UPDATE background_jobs SET lease_expires_at=NULL")
    result = migrate("downgrade", "016_library_recovery")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM tenants WHERE id=?", (tenant,)).fetchone() == ("Keep",)
        assert not db.execute(
            "SELECT name FROM sqlite_master WHERE name='background_jobs'"
        ).fetchone()
    assert migrate("upgrade", "head").returncode == 0
    assert migrate("check").returncode == 0
