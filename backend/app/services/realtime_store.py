"""Short-lived one-use tickets and cross-process connection leases; no resource payloads."""

import hashlib
import json
import secrets
import time

from redis.asyncio import Redis

from app.core.config import settings

RESERVE = """
local now=tonumber(ARGV[1]); local until_at=now+30
for i=1,2 do redis.call('ZREMRANGEBYSCORE',KEYS[i],'-inf',now) end
if redis.call('ZCARD',KEYS[1]) >= tonumber(ARGV[3]) or
   redis.call('ZCARD',KEYS[2]) >= tonumber(ARGV[4]) then return 0 end
for i=1,2 do
  redis.call('ZADD',KEYS[i],until_at,ARGV[2]); redis.call('EXPIRE',KEYS[i],45)
end
return 1
"""
RENEW = """
local now=tonumber(ARGV[1])
for i=1,2 do
  local score=redis.call('ZSCORE',KEYS[i],ARGV[2])
  if not score or tonumber(score) <= now then return 0 end
end
for i=1,2 do
  redis.call('ZADD',KEYS[i],now+30,ARGV[2]); redis.call('EXPIRE',KEYS[i],45)
end
return 1
"""
HANDSHAKE = """
local n=redis.call('INCR',KEYS[1])
if n==1 then redis.call('EXPIRE',KEYS[1],60) end
return n
"""


class LiveStore:
    def __init__(self):
        self.redis = Redis.from_url(
            settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )

    @staticmethod
    def ticket_key(ticket):
        return "cloudvault:live:ticket:" + hashlib.sha256(ticket.encode()).hexdigest()

    @staticmethod
    def lease_keys(identity, ip):
        peer = hashlib.sha256(ip.encode()).hexdigest()
        return (f"cloudvault:live:user:{identity['user_id']}", f"cloudvault:live:ip:{peer}")

    async def issue(self, identity):
        ticket = secrets.token_urlsafe(32)
        if not await self.redis.set(self.ticket_key(ticket), json.dumps(identity), ex=20, nx=True):
            raise RuntimeError("Realtime ticket unavailable")
        return ticket

    async def claim(self, ticket):
        value = await self.redis.getdel(self.ticket_key(ticket))
        return json.loads(value) if value else None

    async def handshake(self, ip):
        peer = hashlib.sha256(ip.encode()).hexdigest()
        return await self.redis.eval(HANDSHAKE, 1, f"cloudvault:live:attempt:{peer}") <= 120

    async def reserve(self, identity, ip, connection):
        return bool(
            await self.redis.eval(
                RESERVE,
                2,
                *self.lease_keys(identity, ip),
                time.time(),
                connection,
                settings.LIVE_USER_CONNECTIONS,
                settings.LIVE_IP_CONNECTIONS,
            )
        )

    async def renew(self, identity, ip, connection):
        return bool(
            await self.redis.eval(RENEW, 2, *self.lease_keys(identity, ip), time.time(), connection)
        )

    async def release(self, identity, ip, connection):
        for key in self.lease_keys(identity, ip):
            await self.redis.zrem(key, connection)

    async def close(self):
        await self.redis.aclose()
