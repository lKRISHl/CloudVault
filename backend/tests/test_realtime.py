"""Phase18 cases are authored for the paired Phase18/18A verification checkpoint."""

import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import select

from app.api.realtime import get_live_store
from app.core.config import settings
from app.core.security import decode_access_token
from app.main import app
from app.models import File, Membership
from app.models.account import LoginSession
from app.models.upload_part import UploadPart
from app.schemas.realtime import LiveSubscribe, LiveTopic
from app.services.auth import AuthService
from app.services.live_snapshots import LiveSnapshots
from app.services.realtime import LiveConnection, origin_allowed
from tests.api.test_auth import register_user
from tests.api.test_files import reserve
from tests.api.test_organizations import add_member, bearer

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def live_origins(monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["http://localhost:3000"])


class MemoryLiveStore:
    """Unit transport dependency; real Redis leases have separate opt-in cases."""

    def __init__(self):
        self.values = {}
        self.released = []

    async def issue(self, identity):
        import secrets

        token = secrets.token_urlsafe(32)
        self.values[token] = identity
        return token

    async def claim(self, token):
        return self.values.pop(token, None)

    async def handshake(self, ip):
        return True

    async def reserve(self, *args):
        return True

    async def renew(self, *args):
        return True

    async def release(self, *args):
        self.released.append(args)


class Socket:
    def __init__(self, frames, origin="http://localhost:3000", query=None):
        self.headers, self.query_params = {"origin": origin}, query or {}
        self.client = SimpleNamespace(host="test-client")
        self.frames, self.sent, self.closed, self.accepted = list(frames), [], None, False

    async def accept(self):
        self.accepted = True

    async def close(self, code):
        self.closed = code

    async def send_json(self, value):
        self.sent.append(value)

    async def receive_text(self):
        if self.frames:
            return self.frames.pop(0)
        raise WebSocketDisconnect()


def identity(session):
    claims = decode_access_token(session["access_token"])
    return {
        "user_id": claims["sub"],
        "tenant_id": claims["tid"],
        "session_id": claims["sid"],
        "until": time.time() + 300,
    }


async def actor(db, session):
    return await AuthService(db).get_user_in_tenant(
        UUID(session["user"]["id"]), UUID(session["user"]["tenant"]["id"])
    )


async def test_ticket_requires_verified_auth_and_is_not_cacheable(client):
    store = MemoryLiveStore()

    async def dependency():
        yield store

    app.dependency_overrides[get_live_store] = dependency
    assert (await client.post("/api/v1/realtime/ticket")).status_code == 401
    unverified = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "unverified-live@example.com",
            "password": "correct-horse",
            "full_name": "Unverified",
            "tenant_name": "Pending verification",
        },
    )
    assert unverified.status_code == 201
    assert (
        await client.post("/api/v1/realtime/ticket", headers=bearer(unverified.json()))
    ).status_code == 403
    owner = await register_user(client)
    response = await client.post("/api/v1/realtime/ticket", headers=bearer(owner))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert len(response.json()["ticket"]) == 43
    principal = await store.claim(response.json()["ticket"])
    assert principal["user_id"] == owner["user"]["id"]
    assert "access_token" not in principal
    assert await store.claim(response.json()["ticket"]) is None


async def test_socket_one_use_first_frame_and_origin_limits(client, db_factory):
    owner = await register_user(client)
    store = MemoryLiveStore()
    ticket = await store.issue(identity(owner))
    hello = json.dumps({"op": "authenticate", "ticket": ticket})
    for socket in (
        Socket([hello], origin="https://foreign.invalid"),
        Socket([hello], query={"token": ticket}),
    ):
        await LiveConnection(socket, store, db_factory).serve()
        assert not socket.accepted and socket.closed == 1008
    good = Socket([hello])
    await LiveConnection(good, store, db_factory).serve()
    assert good.accepted and good.sent[0]["type"] == "ready"
    assert store.released and LiveConnection.active == 0
    replay = Socket([hello])
    await LiveConnection(replay, store, db_factory).serve()
    assert replay.closed == 1008 and not replay.sent


async def test_socket_rechecks_revocation_and_expiry(client, db_factory):
    owner = await register_user(client)
    connection = LiveConnection(Socket([]), MemoryLiveStore(), db_factory)
    connection.identity = identity(owner)
    async with db_factory() as db:
        await connection.authority(db)
    async with db_factory() as db:
        row = await db.get(LoginSession, UUID(connection.identity["session_id"]))
        from datetime import UTC, datetime

        row.revoked_at = datetime.now(UTC)
        await db.commit()
    async with db_factory() as db:
        with pytest.raises(HTTPException) as failure:
            await connection.authority(db)
        assert failure.value.status_code == 401
    connection.identity["until"] = time.time() - 1
    async with db_factory() as db:
        with pytest.raises(HTTPException) as failure:
            await connection.authority(db)
        assert failure.value.status_code == 408


async def test_only_authorized_page_changes_affect_signals(client, db_factory):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    private = await reserve(db_factory, owner, "private-only.pdf")
    assert (
        await client.patch(
            f"/api/v1/files/{private.id}/permissions",
            headers=bearer(owner),
            json={"visibility": "private"},
        )
    ).status_code == 204
    topic = LiveTopic(key="root", kind="files")
    async with db_factory() as db:
        viewer = await actor(db, member)
        before, _ = await LiveSnapshots(db).observe(viewer, topic)
    async with db_factory() as db:
        file = await db.get(File, private.id)
        file.name = "different-private-name.pdf"
        file.name_key = file.name.casefold()
        await db.commit()
    async with db_factory() as db:
        viewer = await actor(db, member)
        after, _ = await LiveSnapshots(db).observe(viewer, topic)
        assert after == before
        with pytest.raises(HTTPException):
            await LiveSnapshots(db).observe(
                viewer, LiveTopic(key="hidden", kind="file", resource_id=private.id)
            )
    visible = await reserve(db_factory, owner, "visible.pdf")
    async with db_factory() as db:
        viewer = await actor(db, member)
        changed, _ = await LiveSnapshots(db).observe(viewer, topic)
        assert changed != before
    assert visible.id != private.id


async def test_progress_counts_only_confirmed_parts_of_own_visible_uploads(client, db_factory):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    file = await reserve(db_factory, owner)
    async with db_factory() as db:
        db.add_all(
            [
                UploadPart(
                    file_id=file.id,
                    number=1,
                    size_bytes=50,
                    checksum_sha256="a" * 44,
                    storage_etag="receipt",
                    confirmed_at=datetime.now(UTC),
                ),
                UploadPart(file_id=file.id, number=2, size_bytes=73, checksum_sha256="b" * 44),
            ]
        )
        await db.commit()
    topic = LiveTopic(key="receipts", kind="files")
    async with db_factory() as db:
        _, own = await LiveSnapshots(db).observe(await actor(db, owner), topic)
        assert own == [{"id": str(file.id), "bytes": 50}]
    async with db_factory() as db:
        _, other = await LiveSnapshots(db).observe(await actor(db, member), topic)
        assert other == []


async def test_membership_loss_closes_authority_and_cross_tenant_resource_is_hidden(
    client, db_factory
):
    owner = await register_user(client)
    outsider = await register_user(client, email="foreign-live@example.com")
    file = await reserve(db_factory, owner)
    async with db_factory() as db:
        foreign = await actor(db, outsider)
        with pytest.raises(HTTPException) as failure:
            await LiveSnapshots(db).observe(
                foreign, LiveTopic(key="foreign", kind="file", resource_id=file.id)
            )
        assert failure.value.status_code == 404
    connection = LiveConnection(Socket([]), MemoryLiveStore(), db_factory)
    connection.identity = identity(owner)
    async with db_factory() as db:
        membership = await db.scalar(
            select(Membership).where(Membership.user_id == UUID(owner["user"]["id"]))
        )
        membership.revoked_at = datetime.now(UTC)
        await db.commit()
    async with db_factory() as db:
        with pytest.raises(HTTPException):
            await connection.authority(db)


async def test_reconnect_baseline_is_opaque_and_denial_does_not_return_data(client, db_factory):
    owner = await register_user(client)
    file = await reserve(db_factory, owner, "never-put-this-name-on-the-socket.pdf")
    socket = Socket([])
    connection = LiveConnection(socket, MemoryLiveStore(), db_factory)
    connection.identity = identity(owner)
    connection.topics = {"file": LiveTopic(key="file", kind="file", resource_id=file.id)}
    await connection.observe()
    assert socket.sent[0]["reason"] == "changed"
    assert "never-put-this-name" not in json.dumps(socket.sent)
    count = len(socket.sent)
    await connection.observe()
    assert socket.sent[count:] == [{"type": "heartbeat"}]
    connection.signatures.clear()  # A new connection must resync even without a replay cursor.
    await connection.observe()
    assert socket.sent[-2]["type"] == "invalidate"


@pytest.mark.parametrize(
    "topics",
    [
        [{"key": "x", "kind": "files", "tenant_id": str(uuid4())}],
        [{"key": "x", "kind": "versions"}],
        [{"key": "x", "kind": "files", "offset": -1}],
        [{"key": "x", "kind": "files"}] * 9,
        [{"key": "same", "kind": "files"}, {"key": "same", "kind": "folders"}],
    ],
)
async def test_subscription_schema_never_accepts_principal_or_unbounded_pages(topics):
    with pytest.raises(ValidationError):
        LiveSubscribe(op="subscribe", topics=topics)


async def test_large_frames_close_before_parsing_without_leaking_slots():
    socket = Socket(["x" * 8193])
    await LiveConnection(socket, MemoryLiveStore(), None).serve()
    assert socket.closed == 1009 and LiveConnection.active == 0


async def test_send_failure_and_excess_commands_release_connection_slots(client, db_factory):
    owner = await register_user(client)
    store = MemoryLiveStore()

    class BrokenSocket(Socket):
        async def send_json(self, value):
            raise RuntimeError("Do not expose private transport data")

    first = await store.issue(identity(owner))
    broken = BrokenSocket([json.dumps({"op": "authenticate", "ticket": first})])
    await LiveConnection(broken, store, db_factory).serve()
    assert broken.closed == 1013 and len(store.released) == 1
    second = await store.issue(identity(owner))
    flood = Socket(
        [json.dumps({"op": "authenticate", "ticket": second})]
        + [json.dumps({"op": "subscribe", "topics": []})] * 61
    )
    await LiveConnection(flood, store, db_factory).serve()
    assert flood.closed == 1008 and LiveConnection.active == 0


async def test_null_and_wildcard_origins_are_not_authorized(monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["http://localhost:3000"])
    assert origin_allowed("http://localhost:3000")
    assert not any(origin_allowed(value) for value in (None, "null", "*", "https://localhost:3000"))
