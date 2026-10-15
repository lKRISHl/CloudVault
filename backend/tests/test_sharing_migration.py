import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_sharing_upgrade_alignment_preservation_and_guarded_rollback(tmp_path):
    test_url, admin = os.getenv("TEST_DATABASE_URL"), None
    database = "cv_sharing_migration_" + uuid4().hex
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
        url = f"sqlite+aiosqlite:///{tmp_path / 'sharing.db'}"
    engine = create_async_engine(url)
    backend = Path(__file__).resolve().parents[1]

    def migrate(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=backend,
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            text=True,
            timeout=30,
        )

    try:
        for args in [
            ("upgrade", "010_file_search"),
            ("upgrade", "head"),
            ("check",),
            ("downgrade", "010_file_search"),
            ("upgrade", "head"),
            ("check",),
        ]:
            result = migrate(*args)
            assert result.returncode == 0, result.stderr
        from datetime import UTC, datetime, timedelta

        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.models import File, ShareLink, Tenant, User

        factory = async_sessionmaker(engine, expire_on_commit=False)
        tid, uid, fid, sid = uuid4(), uuid4(), uuid4(), uuid4()
        async with factory() as db:
            db.add(Tenant(id=tid, name="Preserved", slug="sharing-preserved"))
            db.add(
                User(
                    id=uid,
                    email="sharing@example.com",
                    full_name="Preserved",
                    password_hash="original",
                )
            )
            await db.flush()
            db.add(
                File(
                    id=fid,
                    tenant_id=tid,
                    created_by=uid,
                    name="Preserved.txt",
                    name_key="preserved.txt",
                    declared_size_bytes=7,
                )
            )
            await db.flush()
            db.add(
                ShareLink(
                    id=sid,
                    tenant_id=tid,
                    file_id=fid,
                    created_by=uid,
                    token_hash="a" * 64,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                    allow_download=True,
                )
            )
            await db.commit()
        refused = migrate("downgrade", "010_file_search")
        assert refused.returncode != 0 and "Sharing records exist" in refused.stderr
        assert migrate("upgrade", "head").returncode == 0
        assert migrate("check").returncode == 0
        async with factory() as db:
            assert (await db.get(ShareLink, sid)).token_hash == "a" * 64
            assert (await db.get(File, fid)).name == "Preserved.txt"
            assert (await db.get(User, uid)).password_hash == "original"
        async with engine.connect() as conn:
            assert (
                await conn.scalar(text("SELECT version_num FROM alembic_version"))
                == "016_library_recovery"
            )
    finally:
        await engine.dispose()
        if admin:
            await admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
            await admin.close()
