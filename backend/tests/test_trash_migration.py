import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import File, Folder, Membership, Tenant, User, UserRole
from app.services.trash import TrashService
from tests.migration_seed import seed_file, seed_folder


@pytest.mark.asyncio
async def test_trash_migration_preserves_content_and_guards_history(tmp_path):
    test_url, admin = os.getenv("TEST_DATABASE_URL"), None
    database = "cv_trash_migration_" + uuid4().hex
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
        result = migrate("upgrade", "012_permissions")
        assert result.returncode == 0, result.stderr
        tid, uid, fid = uuid4(), uuid4(), uuid4()
        actor = SimpleNamespace(id=uid, tenant_id=tid)
        async with factory() as db:
            db.add(Tenant(id=tid, name="Preserved", slug="trash-preserved"))
            db.add(
                User(
                    id=uid,
                    email="trash-migration@example.com",
                    full_name="Preserved",
                    password_hash="unchanged",
                    email_verified=True,
                )
            )
            await db.flush()
            db.add(Membership(tenant_id=tid, user_id=uid, role=UserRole.OWNER))
            await seed_file(db, tid, uid, fid, "Existing.txt", 123)
            folder = await seed_folder(db, actor, "Preserved folder")
        for args in [
            ("upgrade", "head"),
            ("check",),
            ("downgrade", "012_permissions"),
            ("upgrade", "head"),
            ("check",),
        ]:
            result = migrate(*args)
            assert result.returncode == 0, result.stderr
        async with factory() as db:
            file = await db.get(File, fid)
            assert (
                file.name == "Existing.txt"
                and file.trash_id is None
                and file.visibility == "workspace"
            )
            assert (await db.get(User, uid)).password_hash == "unchanged"
            entry = await TrashService(db).move_to_trash(actor, "folders", folder.id, "migration")
        refused = migrate("downgrade", "012_permissions")
        assert (
            refused.returncode != 0 and "Trash history or purge references exist" in refused.stderr
        )
        async with factory() as db:
            assert (await db.get(Folder, folder.id)).trash_id == entry.id
            await TrashService(db).restore(actor, entry.id, "migration")
        refused = migrate("downgrade", "012_permissions")
        assert (
            refused.returncode != 0 and "Trash history or purge references exist" in refused.stderr
        )
        assert migrate("check").returncode == 0
    finally:
        await engine.dispose()
        if admin:
            await admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
            await admin.close()
