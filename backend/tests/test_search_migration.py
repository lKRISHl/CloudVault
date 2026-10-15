import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import File, Membership, Tenant, User, UserRole
from app.schemas.search import FileSearchQuery
from app.services.search import FileSearchService
from tests.migration_seed import seed_file


@pytest.mark.asyncio
async def test_search_indexes_preserve_data_and_support_postgres_plans(tmp_path):
    test_url, admin = os.getenv("TEST_DATABASE_URL"), None
    database_name = "cv_search_migration_" + uuid4().hex
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
        url = f"sqlite+aiosqlite:///{tmp_path / 'search.db'}"
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    backend = Path(__file__).resolve().parents[1]

    def migrate(*args):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=backend,
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr

    try:
        migrate("upgrade", "009_upload_cleanup")
        tid, uid, fid = uuid4(), uuid4(), uuid4()
        async with factory() as db:
            db.add(Tenant(id=tid, name="Preserved", slug="search-preserved"))
            db.add(
                User(
                    id=uid,
                    email="preserved-search@example.com",
                    full_name="Preserved",
                    password_hash="original-hash",
                    email_verified=True,
                )
            )
            await db.flush()
            db.add(Membership(tenant_id=tid, user_id=uid, role=UserRole.OWNER))
            await seed_file(db, tid, uid, fid, "Needle.pdf", 123)
            await db.commit()
        for args in [
            ("upgrade", "head"),
            ("check",),
            ("downgrade", "009_upload_cleanup"),
            ("upgrade", "head"),
            ("check",),
        ]:
            migrate(*args)
        async with factory() as db:
            file = await db.get(File, fid)
            assert (
                file.name == "Needle.pdf"
                and file.declared_size_bytes == 123
                and file.object_id is None
            )
            assert (await db.get(User, uid)).password_hash == "original-hash"
        async with engine.connect() as conn:
            indexes = await conn.run_sync(lambda sync: inspect(sync).get_indexes("files"))
            names = {index["name"] for index in indexes}
            assert {
                "ix_files_search_name",
                "ix_files_search_size",
                "ix_files_search_created",
                "ix_files_search_updated",
                "ix_files_search_status",
            } <= names
            assert ("ix_files_search_trgm" in names) == (engine.dialect.name == "postgresql")
        if engine.dialect.name == "postgresql":
            async with factory() as db:
                db.add_all(
                    [
                        File(
                            tenant_id=tid,
                            created_by=uid,
                            name=f"Document-{index:05}.txt",
                            name_key=f"document-{index:05}.txt",
                            declared_size_bytes=index,
                        )
                        for index in range(5000)
                    ]
                )
                await db.commit()
                await db.execute(
                    text("SELECT gin_clean_pending_list('ix_files_search_trgm'::regclass)")
                )
                await db.execute(text("ANALYZE files"))
                from sqlalchemy.dialects import postgresql

                def plan_indexes(plan):
                    found = {plan["Index Name"]} if "Index Name" in plan else set()
                    for child in plan.get("Plans", []):
                        found |= plan_indexes(child)
                    return found

                for query, expected in [
                    (FileSearchQuery(q="needle"), "ix_files_search_trgm"),
                    (FileSearchQuery(sort="size"), "ix_files_search_size"),
                ]:
                    sql = str(
                        FileSearchService.statement(tid, query).compile(
                            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
                        )
                    )
                    result = await db.scalar(text("EXPLAIN (FORMAT JSON) " + sql))
                    assert expected in plan_indexes(result[0]["Plan"]), result
    finally:
        await engine.dispose()
        if admin:
            await admin.execute(f'DROP DATABASE "{database_name}" WITH (FORCE)')
            await admin.close()
