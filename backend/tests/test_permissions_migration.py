import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import File, Membership, ResourceGrant, Tenant, User, UserRole


@pytest.mark.asyncio
async def test_permission_migration_preserves_content_and_refuses_access_loss(tmp_path):
    test_url, admin = os.getenv("TEST_DATABASE_URL"), None
    database = "cv_permission_migration_" + uuid4().hex
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
        url = f"sqlite+aiosqlite:///{tmp_path / 'permissions.db'}"
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    backend = Path(__file__).resolve().parents[1]

    def migrate(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=backend,
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            text=True,
            timeout=40,
        )

    try:
        result = migrate("upgrade", "011_sharing")
        assert result.returncode == 0, result.stderr
        tid, uid, fid = uuid4(), uuid4(), uuid4()
        async with factory() as db:
            db.add(Tenant(id=tid, name="Preserved", slug="permission-preserved"))
            db.add(
                User(
                    id=uid,
                    email="permission@example.com",
                    full_name="Preserved",
                    password_hash="unchanged",
                )
            )
            await db.flush()
            db.add(Membership(tenant_id=tid, user_id=uid, role=UserRole.OWNER))
            old_file = sa.table(
                "files",
                *[sa.column(key, sa.Uuid()) for key in ("id", "tenant_id", "created_by")],
                sa.column("name", sa.String()),
                sa.column("name_key", sa.String()),
                sa.column("declared_size_bytes", sa.BigInteger()),
            )
            await db.execute(
                old_file.insert().values(
                    id=fid,
                    tenant_id=tid,
                    created_by=uid,
                    name="Existing.txt",
                    name_key="existing.txt",
                    declared_size_bytes=123,
                )
            )
            await db.commit()
        for args in [
            ("upgrade", "head"),
            ("check",),
            ("downgrade", "011_sharing"),
            ("upgrade", "head"),
            ("check",),
        ]:
            result = migrate(*args)
            assert result.returncode == 0, result.stderr
        async with factory() as db:
            file = await db.get(File, fid)
            assert (
                file.name == "Existing.txt"
                and file.visibility == "workspace"
                and file.declared_size_bytes == 123
            )
            assert (await db.get(User, uid)).password_hash == "unchanged"
            file.visibility = "private"
            await db.commit()
        refused = migrate("downgrade", "011_sharing")
        assert refused.returncode != 0 and "Private visibility or grants exist" in refused.stderr
        assert migrate("upgrade", "head").returncode == 0
        async with factory() as db:
            file = await db.get(File, fid)
            assert file.visibility == "private"
            file.visibility = "workspace"
            db.add(ResourceGrant(tenant_id=tid, user_id=uid, file_id=fid, role="viewer"))
            await db.commit()
        refused = migrate("downgrade", "011_sharing")
        assert refused.returncode != 0 and "Private visibility or grants exist" in refused.stderr
        assert migrate("upgrade", "head").returncode == 0
        assert migrate("check").returncode == 0
    finally:
        await engine.dispose()
        if admin:
            await admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
            await admin.close()
