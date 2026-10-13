import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.models import RefreshToken, Tenant, User  # noqa: F401


@pytest_asyncio.fixture
async def db_factory(tmp_path):
    # TEST_DATABASE_URL must point to a disposable test database.
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
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
