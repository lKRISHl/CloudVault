import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.models import Folder, Membership, Tenant, User, UserRole
from app.services.auth import AuthService
from app.services.folders import FolderService


@pytest.mark.asyncio
async def test_folder_migration_preserves_accounts_and_refuses_nonempty_downgrade(tmp_path):
    admin = None
    database_name = "cv_folder_migration_" + uuid4().hex
    test_url = os.environ.get("TEST_DATABASE_URL")
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
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        url = parsed.set(database=database_name).render_as_string(hide_password=False)
    else:
        url = f"sqlite+aiosqlite:///{tmp_path / 'folders_migration.db'}"
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
            timeout=30,
        )

    try:
        result = migrate("upgrade", "004_workspaces")
        assert result.returncode == 0, result.stderr
        uid, tid = uuid4(), uuid4()
        original_hash = hash_password("preserved-folder-account")
        async with factory() as db:
            db.add(Tenant(id=tid, name="Preserved", slug="preserved"))
            db.add(
                User(
                    id=uid,
                    email="preserved@example.com",
                    full_name="Preserved",
                    password_hash=original_hash,
                    email_verified=True,
                    is_active=True,
                )
            )
            await db.flush()
            db.add(Membership(tenant_id=tid, user_id=uid, role=UserRole.OWNER))
            await db.commit()
        for args in (("upgrade", "head"), ("check",)):
            result = migrate(*args)
            assert result.returncode == 0, result.stderr
        async with factory() as db:
            actor = await AuthService(db).get_user_in_tenant(uid, tid)
            assert actor.password_hash == original_hash and actor.email_verified
            parent = await FolderService(db).create(actor, "Preserved hierarchy", None)
            child = await FolderService(db).create(actor, "Nested", parent.id)
        rejected = migrate("downgrade", "004_workspaces")
        assert (
            rejected.returncode != 0
            and "Cannot downgrade nonempty folders safely" in rejected.stderr
        )
        async with factory() as db:
            folders = list(await db.scalars(select(Folder)))
            assert len(folders) == 2
            assert (await db.get(Folder, child.id)).parent_id == parent.id
            assert (await db.get(User, uid)).password_hash == original_hash
    finally:
        await engine.dispose()
        if admin:
            await admin.execute(f'DROP DATABASE "{database_name}" WITH (FORCE)')
            await admin.close()
