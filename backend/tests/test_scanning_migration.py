"""Security migration checks on owned SQLite or disposable PostgreSQL databases."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_quarantine_migration_alignment_empty_rollback_and_active_scan_guard(tmp_path):
    source = os.getenv("TEST_DATABASE_URL")
    admin = None
    database = "cv_scan_migration_" + uuid4().hex
    if source and source.startswith("postgresql"):
        import asyncpg

        parsed = make_url(source)
        admin = await asyncpg.connect(
            host=parsed.host,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            database=parsed.database,
        )
        await admin.execute(f'CREATE DATABASE "{database}"')
        url = parsed.set(database=database).render_as_string(hide_password=False)
    else:
        url = f"sqlite+aiosqlite:///{tmp_path / 'quarantine.db'}"

    def migrate(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            text=True,
            timeout=60,
        )

    engine = create_async_engine(url)
    try:
        for args in [
            ("upgrade", "019_preview_jobs"),
            ("upgrade", "head"),
            ("check",),
            ("downgrade", "019_preview_jobs"),
            ("upgrade", "head"),
            ("check",),
        ]:
            result = migrate(*args)
            assert result.returncode == 0, result.stderr
        async with engine.begin() as conn:
            # No file bytes or fabricated content are necessary to test the worker guard.
            await conn.execute(
                sa.text(
                    "INSERT INTO background_jobs(name,runs,failures,lease_id) "
                    "VALUES('scans',0,0,:lease)"
                ),
                {"lease": uuid4().hex},
            )
        result = migrate("downgrade", "019_preview_jobs")
        assert result.returncode != 0 and "Cannot remove quarantine" in result.stderr
        async with engine.begin() as conn:
            assert (
                await conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "020_malware_scanning"
            )
    finally:
        await engine.dispose()
        if admin:
            await admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
            await admin.close()
