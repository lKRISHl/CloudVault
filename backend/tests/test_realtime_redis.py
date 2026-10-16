"""Opt-in real Redis atomic leases. Only generated identities/keys are removed."""

import asyncio
import os
from uuid import uuid4

import pytest

from app.core.config import settings
from app.services.realtime_store import LiveStore

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.getenv("TEST_REDIS_URL"),
        reason="Set TEST_REDIS_URL to a development/test Redis for actual lease checks",
    ),
]


async def test_actual_ticket_getdel_and_global_connection_limits(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", os.environ["TEST_REDIS_URL"])
    monkeypatch.setattr(settings, "LIVE_USER_CONNECTIONS", 1)
    store = LiveStore()
    principal = {
        "user_id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "session_id": str(uuid4()),
        "until": 0,
    }
    ip, first, second = uuid4().hex, uuid4().hex, uuid4().hex
    ticket = None
    try:
        ticket = await store.issue(principal)
        claims = await asyncio.gather(store.claim(ticket), store.claim(ticket))
        assert sum(value is not None for value in claims) == 1
        reserved = await asyncio.gather(
            store.reserve(principal, ip, first), store.reserve(principal, ip, second)
        )
        assert sum(reserved) == 1
        winner = first if reserved[0] else second
        assert await store.renew(principal, ip, winner)
        await store.release(principal, ip, winner)
        assert await store.reserve(principal, ip, second)
        # Simulate an expired score without flushing or deleting any foreign state.
        keys = store.lease_keys(principal, ip)
        for key in keys:
            await store.redis.zadd(key, {second: 0})
        assert not await store.renew(principal, ip, second)
        assert await store.reserve(principal, ip, first)
    finally:
        await store.redis.delete(*store.lease_keys(principal, ip))
        if ticket:
            await store.redis.delete(store.ticket_key(ticket))
        await store.close()
