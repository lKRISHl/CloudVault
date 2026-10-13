import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password, hash_refresh_token
from app.models import Membership, User
from app.services.auth import AuthService


@pytest.mark.asyncio
async def test_global_migration_preserves_identity_live_session_and_removal(tmp_path):
    # PostgreSQL CI/local test runs use a newly created disposable database, never app data.
    test_url = os.environ.get("TEST_DATABASE_URL")
    admin = None
    database_name = "cv_migration_" + uuid4().hex
    if test_url and test_url.startswith("postgresql"):
        import asyncpg

        parsed = sa.make_url(test_url)
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
        url = f"sqlite+aiosqlite:///{tmp_path / 'global_identity.db'}"
    engine = create_async_engine(url)
    environment = {**os.environ, "DATABASE_URL": url}
    backend = Path(__file__).resolve().parents[1]

    def migrate(*args, success=True):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=backend,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if success:
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0
        return result

    tenant_id, owner_id, removed_id, session_id, removed_sid = (uuid4() for _ in range(5))
    suspended_id = uuid4()
    original_hash = hash_password("migration-password")
    raw_refresh = "legacy-refresh-" + uuid4().hex
    expires = datetime.now(UTC) + timedelta(days=2)
    old_jwt = create_access_token(
        user_id=owner_id, tenant_id=tenant_id, role="owner", session_id=session_id
    )
    try:
        migrate("upgrade", "003_accounts")
        async with engine.begin() as connection:
            tables = await connection.run_sync(
                lambda conn: {
                    name: sa.Table(name, sa.MetaData(), autoload_with=conn)
                    for name in (
                        "tenants",
                        "users",
                        "memberships",
                        "login_sessions",
                        "refresh_tokens",
                    )
                }
            )
            for table in tables.values():
                for column in table.columns:
                    if column.name in ("id", "user_id", "tenant_id", "session_id"):
                        column.type = sa.Uuid()
            await connection.execute(
                tables["tenants"].insert().values(id=tenant_id, name="Preserved", slug="preserved")
            )
            for user_id, active, email, role in (
                (owner_id, True, "owner@example.com", "owner"),
                (removed_id, False, "removed@example.com", "member"),
            ):
                await connection.execute(
                    tables["users"]
                    .insert()
                    .values(
                        id=user_id,
                        tenant_id=tenant_id,
                        email=email,
                        full_name="Preserved Identity",
                        password_hash=original_hash,
                        role=role,
                        is_active=active,
                        email_verified=True,
                    )
                )
            await connection.execute(
                tables["memberships"]
                .insert()
                .values(user_id=owner_id, tenant_id=tenant_id, role="owner")
            )
            await connection.execute(
                tables["users"]
                .insert()
                .values(
                    id=suspended_id,
                    tenant_id=tenant_id,
                    email="suspended@example.com",
                    full_name="Suspended",
                    password_hash=original_hash,
                    role="member",
                    is_active=False,
                    email_verified=True,
                )
            )
            await connection.execute(
                tables["memberships"]
                .insert()
                .values(user_id=suspended_id, tenant_id=tenant_id, role="member")
            )
            for user_id, sid in ((owner_id, session_id), (removed_id, removed_sid)):
                await connection.execute(
                    tables["login_sessions"]
                    .insert()
                    .values(id=sid, user_id=user_id, expires_at=expires)
                )
            await connection.execute(
                tables["refresh_tokens"]
                .insert()
                .values(
                    id=uuid4(),
                    user_id=owner_id,
                    session_id=session_id,
                    token_hash=hash_refresh_token(raw_refresh),
                    expires_at=expires,
                )
            )
        migrate("upgrade", "head")
        migrate("check")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            service = AuthService(db)
            uid, tid, sid = service.parse_access_token(old_jwt)
            assert await service.valid_session(uid, sid, tid)
            preserved = await service.get_user_in_tenant(uid, tid)
            assert preserved.email_verified and preserved.password_hash == original_hash
            renewed = await service.refresh(raw_refresh)
            assert renewed.user.tenant_id == tenant_id
            removed = await db.get(User, removed_id)
            assert removed.is_active and removed.password_hash == original_hash
            assert not (await db.get(User, suspended_id)).is_active
            assert await service.get_user_in_tenant(suspended_id, tenant_id) is None
            membership = await db.get(Membership, (tenant_id, removed_id))
            assert membership.revoked_at is not None
            assert not await service.valid_session(removed_id, removed_sid, tenant_id)
            assert await service.get_user_in_tenant(removed_id, tenant_id) is None
        # A second membership makes downgrade explicitly unsafe; it must preserve data.
        async with engine.begin() as connection:
            tenant = await connection.run_sync(
                lambda conn: sa.Table("tenants", sa.MetaData(), autoload_with=conn)
            )
            tenant.c.id.type = sa.Uuid()
            another_id = uuid4()
            await connection.execute(
                tenant.insert().values(id=another_id, name="Additional", slug="additional")
            )
            await connection.execute(
                Membership.__table__.insert().values(
                    tenant_id=another_id, user_id=owner_id, role="owner"
                )
            )
        result = migrate("downgrade", "003_accounts", success=False)
        assert "Cannot downgrade multi-workspace identities safely" in result.stderr
        async with factory() as db:
            assert (
                len(
                    (
                        await db.scalars(
                            sa.select(Membership).where(Membership.user_id == owner_id)
                        )
                    ).all()
                )
                == 2
            )
    finally:
        await engine.dispose()
        if admin:
            await admin.execute(f'DROP DATABASE "{database_name}" WITH (FORCE)')
            await admin.close()
