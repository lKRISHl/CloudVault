"""Disposable E2E backend plus a real loopback SMTP inbox; no production endpoints."""

import asyncio
import contextlib
import json
import os
import socketserver
import sys
import tempfile
import threading
from email import message_from_bytes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
messages = []
messages_lock = threading.Lock()


class SMTPInbox(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b"220 CloudVault disposable inbox\r\n")
        while line := self.rfile.readline():
            verb = line.split(b" ", 1)[0].strip().upper()
            if verb == b"DATA":
                self.wfile.write(b"354 Send message\r\n")
                content = []
                while (line := self.rfile.readline()) != b".\r\n":
                    if not line:
                        return
                    content.append(line)
                mail = message_from_bytes(b"".join(content))
                body = mail.get_payload(decode=True).decode()
                with messages_lock:
                    messages.append({"to": mail["To"], "body": body})
                self.wfile.write(b"250 Accepted\r\n")
            elif verb == b"QUIT":
                self.wfile.write(b"221 Bye\r\n")
                return
            else:
                self.wfile.write(b"250 localhost\r\n")


class InboxHTTP(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/messages":
            self.send_error(404)
            return
        with messages_lock:
            data = json.dumps(messages).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass  # Do not log mailbox contents or secrets.


async def serve():
    import uvicorn
    from app.core.database import async_session_maker, engine
    from app.services.email import deliver_next
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def enforce_test_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def delivery_loop():
        while True:
            async with async_session_maker() as db:
                sent = await deliver_next(db)
            if not sent:
                await asyncio.sleep(0.1)

    dispatcher = asyncio.create_task(delivery_loop())
    try:
        await uvicorn.Server(
            uvicorn.Config(
                "app.main:app",
                host="127.0.0.1",
                port=48000,
                log_level="warning",
                access_log=False,
            )
        ).serve()
    finally:
        dispatcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await dispatcher
        await engine.dispose()


def main():
    with tempfile.TemporaryDirectory(prefix="cloudvault-e2e-") as directory:
        os.environ.update(
            {
                "DATABASE_URL": f"sqlite+aiosqlite:///{Path(directory) / 'accounts.db'}",
                "ENVIRONMENT": "development",
                "SECRET_KEY": "cloudvault-disposable-e2e-secret-not-for-production",
                "SMTP_HOST": "127.0.0.1",
                "SMTP_PORT": "41025",
                "SMTP_STARTTLS": "false",
                "SMTP_USERNAME": "",
                "FRONTEND_URL": "http://127.0.0.1:43000",
                "CORS_ORIGINS": '["http://127.0.0.1:43000"]',
            }
        )
        from alembic import command
        from alembic.config import Config

        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "migrations"))
        command.upgrade(config, "head")
        smtp = socketserver.ThreadingTCPServer(("127.0.0.1", 41025), SMTPInbox)
        http = ThreadingHTTPServer(("127.0.0.1", 48025), InboxHTTP)
        for server in (smtp, http):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            asyncio.run(serve())
        finally:
            for server in (smtp, http):
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    main()
