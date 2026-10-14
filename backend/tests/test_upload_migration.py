import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.models import File, Folder, Membership, Tenant, User, UserRole
from app.schemas.files import FileMetadataCreate
from app.services.auth import AuthService
from app.services.files import FileService
from app.services.folders import FolderService


@pytest.mark.asyncio
async def test_upload_migration_preserves_legacy_metadata_and_guards_upload_references(tmp_path):
    admin = None
    database_name = "cv_upload_migration_" + uuid4().hex
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
        url = f"sqlite+aiosqlite:///{tmp_path / 'uploads_migration.db'}"
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
        result = migrate("upgrade", "005_folders")
        assert result.returncode == 0, result.stderr
        async with factory() as db:
            actor = await AuthService(db).get_user_in_tenant(uid, tid)
            assert actor.password_hash == original_hash and actor.email_verified
            parent = await FolderService(db).create(actor, "Preserved hierarchy", None)
            child = await FolderService(db).create(actor, "Nested", parent.id)
        for args in (
            ("upgrade", "head"),
            ("check",),
            ("downgrade", "005_folders"),
            ("upgrade", "head"),
        ):
            result = migrate(*args)
            assert result.returncode == 0, result.stderr
        async with factory() as db:
            actor = await AuthService(db).get_user_in_tenant(uid, tid)
            assert (await db.get(Folder, child.id)).parent_id == parent.id
            file = await FileService(db).reserve(
                actor,
                FileMetadataCreate(
                    name="Preserved.pdf", folder_id=child.id, declared_size_bytes=123
                ),
            )
        for args in (("downgrade", "006_files"), ("upgrade", "head"), ("check",)):
            result = migrate(*args)
            assert result.returncode == 0, result.stderr
        async with factory() as db:
            legacy = await db.get(File, file.id)
            assert legacy.name == "Preserved.pdf" and legacy.status == "pending"
            assert legacy.object_id is None
            assert legacy.upload_method == "basic" and legacy.checksum_kind == "sha256"
            legacy.object_id = uuid4()
            legacy.storage_bucket = "cv-preserved"
            legacy.upload_request_id = uuid4()
            legacy.expected_checksum_sha256 = "x" * 44
            legacy.upload_expires_at = datetime.now(UTC) + timedelta(minutes=10)
            await db.commit()
        rejected = migrate("downgrade", "006_files")
        assert rejected.returncode != 0 and "Cannot downgrade upload data safely" in rejected.stderr
        restored = migrate("upgrade", "head")
        assert restored.returncode == 0, restored.stderr
        async with factory() as db:
            folders = list(await db.scalars(select(Folder)))
            assert len(folders) == 2
            assert (await db.get(File, file.id)).folder_id == child.id
            assert (await db.get(File, file.id)).object_id is not None
            assert (await db.get(Folder, child.id)).parent_id == parent.id
            assert (await db.get(User, uid)).password_hash == original_hash
    finally:
        await engine.dispose()
        if admin:
            await admin.execute(f'DROP DATABASE "{database_name}" WITH (FORCE)')
            await admin.close()
