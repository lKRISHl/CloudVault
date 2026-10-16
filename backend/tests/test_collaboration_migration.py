"""Owned SQLite migration acceptance, queued for18A+20."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_collaboration_empty_rollback_and_nonempty_guard(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'collaboration.db'}"

    def migrate(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            text=True,
            timeout=60,
        )

    assert migrate("upgrade", "022_collaboration").returncode == 0
    assert migrate("check").returncode == 0
    assert migrate("downgrade", "021_storage_quotas").returncode == 0
    assert migrate("upgrade", "022_collaboration").returncode == 0
    engine = create_async_engine(url)
    try:
        async with engine.begin() as db:
            # This migration-only connection has SQLite FK enforcement disabled; no app data.
            await db.execute(
                text(
                    "INSERT INTO resource_owners(id,tenant_id,file_id,user_id) VALUES (:id,:tenant,:file,:user)"
                ),
                {key: uuid4().hex for key in ("id", "tenant", "file", "user")},
            )
        result = migrate("downgrade", "021_storage_quotas")
        assert result.returncode != 0 and "cannot be represented" in result.stderr
        async with engine.begin() as db:
            assert await db.scalar(text("SELECT count(*) FROM resource_owners")) == 1
    finally:
        await engine.dispose()
