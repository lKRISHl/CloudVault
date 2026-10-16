import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4


def test_intent_migration_preserves_unknown_location_and_guards_lossy_rollback(tmp_path):
    path = tmp_path / "intent-migration.db"

    def migrate(*arguments):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}"},
            capture_output=True,
            text=True,
            timeout=45,
        )

    assert migrate("upgrade", "017_background_jobs").returncode == 0
    file_id, tenant, object_id, creator, request = [uuid4().hex for _ in range(5)]
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO upload_intents (file_id,tenant_id,object_id,created_by,request_id,"
            "storage_bucket,fingerprint,expires_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                file_id,
                tenant,
                object_id,
                creator,
                request,
                "old-bucket",
                "0" * 64,
                "2026-10-16 12:00:00",
            ),
        )
    result = migrate("upgrade", "head")
    assert result.returncode == 0, result.stderr
    result = migrate("check")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT object_id,folder_id,cancelled_at,expires_at,scope_recorded "
            "FROM upload_intents WHERE file_id=?",
            (file_id,),
        ).fetchone() == (object_id, None, None, "2026-10-16 12:00:00", 0)
    assert migrate("downgrade", "017_background_jobs").returncode == 0
    assert migrate("upgrade", "head").returncode == 0
    for column, value in (
        ("folder_id", uuid4().hex),
        ("cancelled_at", "2026-10-16 11:00:00"),
        ("scope_recorded", 1),
    ):
        with sqlite3.connect(path) as db:
            db.execute(
                "UPDATE upload_intents SET folder_id=NULL,cancelled_at=NULL,scope_recorded=0"
            )
            # Column names are fixed test constants, never input from an operator.
            db.execute(f"UPDATE upload_intents SET {column}=?", (value,))
        result = migrate("downgrade", "017_background_jobs")
        assert result.returncode != 0 and "cannot be discarded" in result.stderr
