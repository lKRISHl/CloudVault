import queue
import socketserver
import threading
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.models.account import EmailOutbox
from app.services.email import deliver_next, queue_email
from tests.api.test_auth import REGISTER_PAYLOAD


@pytest.fixture
def smtp_inbox(monkeypatch):
    inbox = queue.Queue()

    class SMTPHandler(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b"220 local test inbox\r\n")
            while line := self.rfile.readline():
                command = line.split(b" ", 1)[0].strip().upper()
                if command == b"DATA":
                    self.wfile.write(b"354 send message\r\n")
                    lines = []
                    while (line := self.rfile.readline()) != b".\r\n":
                        if not line:
                            return
                        lines.append(line)
                    inbox.put(b"".join(lines))
                    self.wfile.write(b"250 accepted\r\n")
                elif command == b"QUIT":
                    self.wfile.write(b"221 bye\r\n")
                    return
                else:
                    self.wfile.write(b"250 localhost\r\n")

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), SMTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "SMTP_PORT", server.server_address[1])
    monkeypatch.setattr(settings, "SMTP_STARTTLS", False)
    try:
        yield inbox
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.asyncio
async def test_real_smtp_delivery_of_verification_then_verify(client, db_factory, smtp_inbox):
    response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert not response.json()["user"]["email_verified"]
    async with db_factory() as db:
        assert await deliver_next(db)
        mail = (await db.scalars(select(EmailOutbox))).one()
        assert mail.sent_at is not None and mail.encrypted_payload is None
    from email import message_from_bytes

    received = message_from_bytes(smtp_inbox.get(timeout=3))
    assert received["To"] == REGISTER_PAYLOAD["email"]
    body = received.get_payload(decode=True).decode()
    link = next(line for line in body.splitlines() if line.startswith("http"))
    token = parse_qs(urlsplit(link).fragment)["token"][0]
    assert (await client.post("/api/v1/account/verify", json={"token": token})).status_code == 200


@pytest.mark.asyncio
async def test_delivery_failure_is_recorded_and_retry_delivers_one_message(
    db_factory, smtp_inbox, monkeypatch
):
    async with db_factory() as db:
        mail = queue_email(
            db, None, "notification", "recipient@example.com", "Test", "Test message"
        )
        await db.commit()
        original_port = settings.SMTP_PORT
        monkeypatch.setattr(settings, "SMTP_PORT", 1)
        assert await deliver_next(db)
        await db.refresh(mail)
        assert mail.sent_at is None and mail.error_code == "delivery_failed" and mail.attempts == 1
        assert mail.encrypted_payload is not None
        monkeypatch.setattr(settings, "SMTP_PORT", original_port)
        await db.execute(
            update(EmailOutbox).values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await db.commit()
        assert await deliver_next(db)
        assert not await deliver_next(db)
        assert smtp_inbox.qsize() == 1


@pytest.mark.asyncio
async def test_queued_mail_never_verifies_user_and_expired_delivery_purges_payload(
    client, db_factory
):
    registered = (await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)).json()
    async with db_factory() as db:
        await db.execute(
            update(EmailOutbox).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await db.commit()
        assert not await deliver_next(db)
        mail = (await db.scalars(select(EmailOutbox))).one()
        assert mail.error_code == "delivery_expired" and mail.encrypted_payload is None
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {registered['access_token']}"}
    )
    assert not me.json()["email_verified"]
