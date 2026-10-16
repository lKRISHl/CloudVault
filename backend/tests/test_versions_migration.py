import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import File, FileVersion, Tenant, User


@pytest.mark.asyncio
async def test_versions_backfill_objects_empty_rollback_and_retained_reference_guard(tmp_path):
    test_url, admin = os.getenv("TEST_DATABASE_URL"), None
    database = "cv_versions_migration_" + uuid4().hex
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
        url = f"sqlite+aiosqlite:///{tmp_path / 'versions.db'}"
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
        assert migrate("upgrade", "013_trash").returncode == 0
        tid, uid, fid, oid, rid = [uuid4() for _ in range(5)]
        async with factory() as db:
            db.add(Tenant(id=tid, name="Versions", slug="preserved-versions"))
            db.add(
                User(
                    id=uid,
                    email="version-migration@example.com",
                    full_name="Preserved",
                    password_hash="original",
                )
            )
            await db.commit()
        async with engine.begin() as conn:
            table = await conn.run_sync(
                lambda sync: sa.Table("files", sa.MetaData(), autoload_with=sync)
            )
            for key in ("id", "tenant_id", "created_by", "object_id", "upload_request_id"):
                table.c[key].type = sa.Uuid()
            await conn.execute(
                table.insert().values(
                    id=fid,
                    tenant_id=tid,
                    created_by=uid,
                    name="Preserved.txt",
                    name_key="preserved.txt",
                    declared_size_bytes=7,
                    status="uploaded",
                    object_id=oid,
                    storage_bucket="preserved-bucket",
                    upload_request_id=rid,
                    upload_expires_at=datetime.now(UTC) + timedelta(hours=1),
                    expected_checksum_sha256="a" * 44,
                    size_bytes=7,
                    checksum_sha256="a" * 44,
                    content_type="application/octet-stream",
                    storage_etag='"original"',
                    completed_at=datetime.now(UTC),
                )
            )
        for args in [
            ("upgrade", "head"),
            ("check",),
            ("downgrade", "013_trash"),
            ("upgrade", "head"),
            ("check",),
        ]:
            result = migrate(*args)
            if args[0] == "downgrade":
                assert result.returncode != 0 and "Cannot remove quarantine" in result.stderr
            else:
                assert result.returncode == 0, result.stderr
        async with factory() as db:
            file = await db.get(File, fid)
            initial = await db.scalar(sa.select(FileVersion).where(FileVersion.file_id == fid))
            assert file.current_version == file.version_generation == 1
            assert file.scan_status == initial.scan_status == "pending"
            assert (
                initial.object_id == file.object_id == oid and initial.storage_etag == '"original"'
            )
            db.add(
                FileVersion(
                    tenant_id=tid,
                    file_id=fid,
                    number=2,
                    base_generation=1,
                    created_by=uid,
                    request_id=uuid4(),
                    status="pending",
                    object_id=uuid4(),
                    storage_bucket="preserved-bucket",
                    upload_expires_at=datetime.now(UTC),
                    declared_size_bytes=8,
                    expected_checksum_sha256="b" * 44,
                )
            )
            await db.commit()
        refused = migrate("downgrade", "013_trash")
        assert (
            refused.returncode != 0
            and "Cannot remove quarantine" in refused.stderr
        )
        assert migrate("upgrade", "head").returncode == 0
        assert migrate("check").returncode == 0
        async with factory() as db:
            assert len(list(await db.scalars(sa.select(FileVersion)))) == 2
            assert (await db.get(File, fid)).object_id == oid
    finally:
        await engine.dispose()
        if admin:
            await admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
            await admin.close()
