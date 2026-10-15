import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import File, Tenant, User


@pytest.mark.asyncio
async def test_recovery_migration_preserves_legacy_rows_and_guards_discard_rollback(tmp_path):
    test_url, admin = os.getenv("TEST_DATABASE_URL"), None
    database = "cv_library_recovery_" + uuid4().hex
    if test_url and test_url.startswith("postgresql"):
        import asyncpg

        parsed = make_url(test_url)
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
        url = f"sqlite+aiosqlite:///{tmp_path / 'recovery.db'}"
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    def migrate(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            text=True,
            timeout=40,
        )

    try:
        assert migrate("upgrade", "015_version_transfers").returncode == 0
        tid, uid, fid = uuid4(), uuid4(), uuid4()
        async with factory() as db:
            db.add(Tenant(id=tid, name="Legacy", slug="legacy-recovery"))
            db.add(
                User(
                    id=uid,
                    email="legacy-recovery@example.com",
                    full_name="Preserved",
                    password_hash="original",
                )
            )
            await db.commit()
        async with engine.begin() as conn:
            table = await conn.run_sync(
                lambda sync: sa.Table("files", sa.MetaData(), autoload_with=sync)
            )
            for key in ("id", "tenant_id", "created_by"):
                table.c[key].type = sa.Uuid()
            await conn.execute(
                table.insert().values(
                    id=fid,
                    tenant_id=tid,
                    created_by=uid,
                    name="Legacy.txt",
                    name_key="legacy.txt",
                    declared_size_bytes=123,
                    status="pending",
                )
            )
        for args in [
            ("upgrade", "head"),
            ("check",),
            ("downgrade", "015_version_transfers"),
            ("upgrade", "head"),
            ("check",),
        ]:
            result = migrate(*args)
            assert result.returncode == 0, result.stderr
        async with factory() as db:
            file = await db.get(File, fid)
            assert file.name == "Legacy.txt" and file.object_id is None
            assert file.declared_size_bytes == 123 and file.upload_cancelled_at is None
            file.upload_cancelled_at = file.upload_cleanup_at = datetime.now(UTC)
            await db.commit()
        refused = migrate("downgrade", "015_version_transfers")
        assert refused.returncode != 0 and "cancellation/discard history" in refused.stderr
        assert migrate("check").returncode == 0
        async with factory() as db:
            file = await db.get(File, fid)
            assert file.upload_cleanup_at and file.upload_cancelled_at and file.object_id is None
    finally:
        await engine.dispose()
        if admin:
            await admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
            await admin.close()
