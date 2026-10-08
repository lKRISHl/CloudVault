"""Tests for health check endpoints."""

import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.asyncio
async def test_liveness_returns_ok(client: AsyncClient):
    """Liveness endpoint should always return 200 with status ok."""
    response = await client.get(f"{settings.API_V1_PREFIX}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == settings.APP_VERSION
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_liveness_content_type(client: AsyncClient):
    """Liveness endpoint should return JSON."""
    response = await client.get(f"{settings.API_V1_PREFIX}/health")
    assert "application/json" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_readiness_structure(client: AsyncClient):
    """Readiness endpoint should return structured check results."""
    response = await client.get(f"{settings.API_V1_PREFIX}/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "checks" in data
    assert "database" in data["checks"]
    assert data["checks"]["database"]["status"] in ("up", "down")
    assert data["version"] == settings.APP_VERSION
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_db_down_without_postgres(client: AsyncClient):
    """Without a running PostgreSQL, readiness should report degraded with DB down."""
    response = await client.get(f"{settings.API_V1_PREFIX}/health/ready")
    data = response.json()
    # No PostgreSQL running in test environment
    assert data["status"] == "degraded"
    assert data["checks"]["database"]["status"] == "down"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Root endpoint should return app name and version."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == settings.APP_NAME
    assert data["version"] == settings.APP_VERSION
