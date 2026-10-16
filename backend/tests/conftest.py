import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.models import RefreshToken, Tenant, User  # noqa: F401


@pytest_asyncio.fixture(autouse=True)
async def legacy_successful_scan_dependency(request, monkeypatch):
    """Prior resource tests isolate their original contracts under a successful scan boundary.

    Scan-enforcement tests keep the real release gate; actual ClamAV/queue/browser acceptance
    is separate. This fixture never changes application configuration or shipped behavior.
    """
    # Freeze the legacy dependency substitution to the original resource modules.
    # New modules exercise the real gate by default; never silently exempt future tests.
    legacy_modules = {
        "test_downloads",
        "test_previews",
        "test_preview_jobs",
        "test_shares",
        "test_versions",
        "test_version_transfers",
        "test_permissions",
        "test_uploads_integration",
        "test_versions_integration",
        "test_version_transfers_integration",
        "test_previews_integration",
        "test_library_recovery_integration",
        "test_trash_integration",
        "test_library_recovery",
        "test_trash",
        "test_multipart_integration",
    }
    if (
        request.module.__name__.rsplit(".", 1)[-1] in legacy_modules
        and request.node.get_closest_marker("scan_enforcement") is None
    ):

        async def released(*args, **kwargs):
            return None

        monkeypatch.setattr("app.services.scans.require_released", released)


@pytest_asyncio.fixture
async def db_factory(tmp_path):
    # TEST_DATABASE_URL must point to a disposable test database.
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    engine = create_async_engine(url)
    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    async with engine.begin() as conn:
        if url.startswith("postgresql"):
            from sqlalchemy import text

            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield session_maker
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def client(db_factory) -> AsyncGenerator[AsyncClient, None]:

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with db_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
