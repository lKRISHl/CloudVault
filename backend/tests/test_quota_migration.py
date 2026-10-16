"""Owned SQLite migration preservation; PostgreSQL acceptance uses a disposable DB."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_quota_upgrade_preserves_legacy_unknown_intent_and_guards_rollback(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'quota-migration.db'}"

    def migrate(*args):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result

    for args in (("upgrade", "head"), ("check",), ("downgrade", "020_malware_scanning")):
        result = migrate(*args)
        assert result.returncode == 0, result.stderr
    engine = create_async_engine(url)
    try:
        tid, fid = uuid4().hex, uuid4().hex
        async with engine.begin() as db:
            await db.execute(
                text("INSERT INTO tenants (id,name,slug) VALUES (:id,'Legacy','legacy')"),
                {"id": tid},
            )
            await db.execute(
                text("""INSERT INTO upload_intents
                (file_id,tenant_id,object_id,created_by,request_id,storage_bucket,fingerprint,expires_at)
                VALUES (:fid,:tid,:object,:creator,:request,'legacy','aaaaaaaa',CURRENT_TIMESTAMP)
            """),
                {
                    "fid": fid,
                    "tid": tid,
                    "object": uuid4().hex,
                    "creator": uuid4().hex,
                    "request": uuid4().hex,
                },
            )
        result = migrate("upgrade", "head")
        assert result.returncode == 0, result.stderr
        assert migrate("check").returncode == 0
        async with engine.begin() as db:
            assert await db.scalar(text("SELECT count(*) FROM upload_intents")) == 1
            assert await db.scalar(text("SELECT reserved_bytes FROM upload_intents")) is None
            assert await db.scalar(text("SELECT storage_plan FROM storage_quotas")) == "free"
        result = migrate("downgrade", "020_malware_scanning")
        assert result.returncode == 0, result.stderr
        assert migrate("upgrade", "head").returncode == 0
        async with engine.begin() as db:
            await db.execute(text("UPDATE storage_quotas SET storage_limit_bytes=0"))
        result = migrate("downgrade", "020_malware_scanning")
        assert result.returncode != 0 and "Quota rollback would lose" in result.stderr
    finally:
        await engine.dispose()
