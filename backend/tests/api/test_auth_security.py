import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from app.core.config import Settings, settings
from app.core.security import create_access_token, hash_refresh_token, verify_password
from app.models import RefreshToken, User
from app.services.auth import AuthService
from tests.api.test_auth import REGISTER_PAYLOAD, register_user


@pytest.mark.parametrize("secret", ["short", "change-me-in-development-only-32bytes-min"])
def test_production_rejects_unsafe_secret(secret):
    with pytest.raises(ValueError, match="Production requires"):
        Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY=secret)


def test_production_accepts_custom_secret():
    config = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="a" * 64,
        SMTP_STARTTLS=True,
        FRONTEND_URL="https://cloudvault.example",
    )
    assert config.is_production


@pytest.mark.asyncio
async def test_registration_stores_hashes_and_secure_cookie(client, db_factory):
    response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 201
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "path=/api/v1/auth" in cookie
    raw = client.cookies.get(settings.REFRESH_COOKIE_NAME)
    async with db_factory() as db:
        user = (await db.execute(select(User))).scalar_one()
        token = (await db.execute(select(RefreshToken))).scalar_one()
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password(REGISTER_PAYLOAD["password"], user.password_hash)
        assert token.token_hash == hash_refresh_token(raw)
        assert token.token_hash != raw
    assert "password_hash" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["expired", "bad-signature", "malformed", "missing-exp"])
async def test_invalid_access_tokens_are_rejected(client, kind):
    owner = await register_user(client)
    claims = {
        "sub": owner["user"]["id"],
        "tid": owner["user"]["tenant"]["id"],
        "typ": "access",
        "exp": datetime.now(UTC) + timedelta(minutes=1),
        "sid": jwt.decode(owner["access_token"], options={"verify_signature": False})["sid"],
    }
    if kind == "expired":
        claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    if kind == "missing-exp":
        del claims["exp"]
    secret = (
        "different-signing-secret-of-at-least-32-bytes"
        if kind == "bad-signature"
        else settings.SECRET_KEY
    )
    token = "not-a-jwt" if kind == "malformed" else jwt.encode(claims, secret, algorithm="HS256")
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_existing_user_cannot_access_another_tenant(client):
    first = await register_user(client)
    second = await register_user(client, email="second@example.com", tenant_name="Other Workspace")
    token = create_access_token(
        user_id=UUID(first["user"]["id"]),
        tenant_id=UUID(second["user"]["tenant"]["id"]),
        role="owner",
        session_id=UUID(
            jwt.decode(first["access_token"], options={"verify_signature": False})["sid"]
        ),
    )
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_disabled_user_cannot_login_refresh_or_access_profile(client, db_factory):
    owner = await register_user(client)
    async with db_factory() as db:
        await db.execute(update(User).values(is_active=False))
        await db.commit()
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={
                "email": REGISTER_PAYLOAD["email"],
                "password": REGISTER_PAYLOAD["password"],
            },
        )
    ).status_code == 401
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {owner['access_token']}",
            },
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_expired_refresh_token_is_rejected(client, db_factory):
    await register_user(client)
    async with db_factory() as db:
        await db.execute(
            update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(days=1))
        )
        await db.commit()
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


@pytest.mark.asyncio
async def test_concurrent_refresh_has_exactly_one_winner(client, db_factory, monkeypatch):
    await register_user(client)
    raw = client.cookies.get(settings.REFRESH_COOKIE_NAME)
    ready = asyncio.Event()
    arrivals = 0

    async def attempt():
        nonlocal arrivals
        async with db_factory() as db:
            original_execute = db.execute
            first_read = True

            async def execute(*args, **kwargs):
                nonlocal arrivals, first_read
                result = await original_execute(*args, **kwargs)
                if first_read:
                    first_read = False
                    arrivals += 1
                    if arrivals == 2:
                        ready.set()
                    await asyncio.wait_for(ready.wait(), timeout=10)
                return result

            monkeypatch.setattr(db, "execute", execute)
            try:
                return await AuthService(db).refresh(raw)
            except HTTPException as exc:
                return exc.status_code

    outcomes = await asyncio.wait_for(asyncio.gather(attempt(), attempt()), timeout=20)
    assert sum(isinstance(result, int) and result == 401 for result in outcomes) == 1
    async with db_factory() as db:
        tokens = (await db.execute(select(RefreshToken))).scalars().all()
        assert len(tokens) == 2
        assert sum(token.revoked_at is None for token in tokens) == 1
