from uuid import UUID, uuid4

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.security import create_access_token

REGISTER_PAYLOAD = {
    "email": "owner@example.com",
    "password": "correct-horse",
    "full_name": "Ada Lovelace",
    "tenant_name": "Analytical Engines",
}


async def register_user(client: AsyncClient, **overrides: str) -> dict:
    payload = {**REGISTER_PAYLOAD, **overrides}
    response = await client.post(f"{settings.API_V1_PREFIX}/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_register_creates_owner_and_sets_refresh_cookie(client: AsyncClient):
    response = await client.post(f"{settings.API_V1_PREFIX}/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 201
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["user"]["email"] == "owner@example.com"
    assert data["user"]["role"] == "owner"
    assert data["user"]["tenant"]["name"] == "Analytical Engines"
    assert data["user"]["tenant"]["slug"] == "analytical-engines"
    assert settings.REFRESH_COOKIE_NAME in response.cookies


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(client: AsyncClient):
    await register_user(client)
    response = await client.post(f"{settings.API_V1_PREFIX}/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_rejects_short_password(client: AsyncClient):
    response = await client.post(
        f"{settings.API_V1_PREFIX}/auth/register",
        json={**REGISTER_PAYLOAD, "password": "short"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_and_me(client: AsyncClient):
    await register_user(client)
    login = await client.post(
        f"{settings.API_V1_PREFIX}/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = await client.get(
        f"{settings.API_V1_PREFIX}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"


@pytest.mark.asyncio
async def test_login_rejects_bad_password(client: AsyncClient):
    await register_user(client)
    response = await client.post(
        f"{settings.API_V1_PREFIX}/auth/login",
        json={"email": "owner@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    response = await client.get(f"{settings.API_V1_PREFIX}/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_cookie(client: AsyncClient):
    await register_user(client)
    first = client.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert first

    refreshed = await client.post(f"{settings.API_V1_PREFIX}/auth/refresh")
    assert refreshed.status_code == 200
    second = client.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert second
    assert second != first

    client.cookies.clear()
    client.cookies.set(settings.REFRESH_COOKIE_NAME, first)
    replay = await client.post(f"{settings.API_V1_PREFIX}/auth/refresh")
    assert replay.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client: AsyncClient):
    await register_user(client)
    logout = await client.post(f"{settings.API_V1_PREFIX}/auth/logout")
    assert logout.status_code == 204

    refreshed = await client.post(f"{settings.API_V1_PREFIX}/auth/refresh")
    assert refreshed.status_code == 401


@pytest.mark.asyncio
async def test_access_token_is_tenant_scoped(client: AsyncClient):
    owner = await register_user(client)
    forged = create_access_token(
        user_id=uuid4(),
        tenant_id=UUID(owner["user"]["tenant"]["id"]),
        role="owner",
    )
    response = await client.get(
        f"{settings.API_V1_PREFIX}/auth/me",
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_token_rejects_wrong_type(client: AsyncClient):
    await register_user(client)
    token = jwt.encode(
        {"sub": str(uuid4()), "tid": str(uuid4()), "role": "owner", "typ": "refresh"},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    response = await client.get(
        f"{settings.API_V1_PREFIX}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
