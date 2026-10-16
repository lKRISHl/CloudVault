"""Session-bound WebSocket observations with fresh authority on every observation."""

import asyncio
import time
from collections import deque
from contextlib import suppress
from uuid import UUID, uuid4

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import settings
from app.schemas.auth import UserRead
from app.schemas.realtime import LiveHello, LiveSubscribe
from app.services.accounts import AccountService
from app.services.auth import AuthService
from app.services.live_snapshots import LiveSnapshots, digest


async def issue_ticket(db, store, actor, session_id, ip):
    await AccountService(db).limit(
        "realtime-ticket", ip, str(actor.id), max_identity=120, max_ip=1200
    )
    try:
        value = await store.issue(
            {
                "user_id": str(actor.id),
                "tenant_id": str(actor.tenant_id) if actor.tenant_id else None,
                "session_id": str(session_id),
                "until": time.time() + 300,
            }
        )
    except Exception:
        raise HTTPException(503, "Realtime unavailable; manual refresh remains available") from None
    return {"ticket": value, "expires_in": 20}


class LivePrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    tenant_id: UUID | None
    session_id: UUID
    until: float


def origin_allowed(origin):
    return bool(
        origin
        and origin != "null"
        and origin in {str(value).rstrip("/") for value in settings.CORS_ORIGINS}
    )


class LiveConnection:
    active = 0

    def __init__(self, socket: WebSocket, store, factory):
        self.socket, self.store, self.factory = socket, store, factory
        self.connection = uuid4().hex
        self.ip = socket.client.host if socket.client else "unknown"
        self.identity = None
        self.topics, self.signatures = {}, {}
        self.identity_digest = None
        self.commands = deque()

    async def send(self, value):
        await asyncio.wait_for(self.socket.send_json(value), 2)

    async def authority(self, db):
        principal = LivePrincipal.model_validate(self.identity)
        if principal.until <= time.time():
            raise HTTPException(408, "Realtime capability expired")
        auth = AuthService(db)
        actor = await auth.get_user_in_tenant(principal.user_id, principal.tenant_id)
        if (
            actor is None
            or not actor.email_verified
            or not await auth.valid_session(
                principal.user_id, principal.session_id, principal.tenant_id
            )
        ):
            raise HTTPException(401, "Realtime session unavailable")
        return actor

    async def observe(self):
        messages = []
        async with self.factory() as db:
            actor = await self.authority(db)
            identity_digest = digest(UserRead.model_validate(actor))
            if self.identity_digest and self.identity_digest != identity_digest:
                messages.append({"type": "identity_changed"})
            self.identity_digest = identity_digest
            snapshots = LiveSnapshots(db)
            for key, topic in self.topics.items():
                try:
                    value, progress = await snapshots.observe(actor, topic)
                except HTTPException as error:
                    if error.status_code not in (403, 404, 409, 410, 423):
                        raise
                    value, progress = "unavailable", []
                if self.signatures.get(key) != value:
                    messages.append(
                        {
                            "type": "invalidate",
                            "key": key,
                            "reason": "unavailable" if value == "unavailable" else "changed",
                            "progress": progress,
                        }
                    )
                    self.signatures[key] = value
            # End read transactions before awaiting slow clients. No provider I/O occurs.
            await db.rollback()
        for message in messages:
            await self.send(message)
        await self.send({"type": "heartbeat"})

    async def serve(self):
        if (
            not origin_allowed(self.socket.headers.get("origin"))
            or self.socket.query_params
            or LiveConnection.active >= settings.LIVE_PROCESS_CONNECTIONS
        ):
            await self.socket.close(code=1008)
            return
        LiveConnection.active += 1
        reserved = False
        try:
            if not await self.store.handshake(self.ip):
                await self.socket.close(code=1013)
                return
            await self.socket.accept()
            raw = await asyncio.wait_for(self.socket.receive_text(), 5)
            if len(raw.encode()) > 8192:
                await self.socket.close(code=1009)
                return
            hello = LiveHello.model_validate_json(raw)
            self.identity = await self.store.claim(hello.ticket)
            principal = LivePrincipal.model_validate(self.identity)
            if not time.time() < principal.until <= time.time() + 301:
                raise HTTPException(401, "Realtime ticket unavailable")
            async with self.factory() as db:
                actor = await self.authority(db)
                self.identity_digest = digest(UserRead.model_validate(actor))
            reserved = await self.store.reserve(self.identity, self.ip, self.connection)
            if not reserved:
                await self.socket.close(code=4429)
                return
            await self.send({"type": "ready", "poll_seconds": settings.LIVE_POLL_SECONDS})
            next_poll = time.monotonic()
            while True:
                if time.monotonic() >= next_poll:
                    if not await self.store.renew(self.identity, self.ip, self.connection):
                        raise HTTPException(503, "Realtime lease lost")
                    async with asyncio.timeout(10):
                        await self.observe()
                    next_poll = time.monotonic() + settings.LIVE_POLL_SECONDS
                try:
                    raw = await asyncio.wait_for(
                        self.socket.receive_text(), max(0.01, next_poll - time.monotonic())
                    )
                except TimeoutError:
                    continue
                if len(raw.encode()) > 8192:
                    await self.socket.close(code=1009)
                    return
                now = time.monotonic()
                while self.commands and self.commands[0] < now - 60:
                    self.commands.popleft()
                if len(self.commands) >= 60:
                    await self.socket.close(code=1008)
                    return
                self.commands.append(now)
                update = LiveSubscribe.model_validate_json(raw)
                topics = {topic.key: topic for topic in update.topics}
                # Changing the parameters of a reused key requires a fresh authorized baseline.
                self.signatures = {
                    key: value
                    for key, value in self.signatures.items()
                    if key in topics and self.topics.get(key) == topics[key]
                }
                self.topics = topics
                # Commands cannot postpone session/membership checks indefinitely.
        except WebSocketDisconnect:
            pass
        except HTTPException as error:
            with suppress(Exception):
                await self.socket.close(
                    code=4401
                    if error.status_code == 401
                    else 4408
                    if error.status_code == 408
                    else 1013
                )
        except (ValidationError, ValueError, KeyError, TypeError):
            with suppress(Exception):
                await self.socket.close(code=1008)
        except Exception:
            # Never log ticket frames, query results or SDK/SQL exception text.
            with suppress(Exception):
                await self.socket.close(code=1013)
        finally:
            try:
                if reserved:
                    with suppress(Exception):
                        await asyncio.wait_for(
                            self.store.release(self.identity, self.ip, self.connection), 2
                        )
            finally:
                LiveConnection.active -= 1
