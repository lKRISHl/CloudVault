"""Health check endpoints for liveness and readiness probes."""

import time
from datetime import UTC, datetime

from fastapi import APIRouter

from app.core.config import settings
from app.core.database import check_db_connection

router = APIRouter()


@router.get("")
async def liveness():
    """Liveness probe — confirms the service is running."""
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/ready")
async def readiness():
    """Readiness probe — checks connectivity to dependent services."""
    start = time.monotonic()
    db_ok = await check_db_connection()
    db_latency_ms = round((time.monotonic() - start) * 1000, 2)

    db_check = {
        "status": "up" if db_ok else "down",
    }
    if db_ok:
        db_check["latency_ms"] = db_latency_ms

    overall = "ok" if db_ok else "degraded"

    return {
        "status": overall,
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": {
            "database": db_check,
        },
    }
