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
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
STORAGE_MANIFEST = BACKEND.parent / ".local" / "e2e-storage.json"
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

    if os.getenv("TEST_PREVIEW_FIXTURE_RENDERER") == "1":
        # Owned generated fixtures only. Production/API code never falls back to host parsing.
        # The live Docker smoke separately verifies the network-disabled container boundary.
        from app.schemas.previews import PreviewContent
        from app.services import previews

        async def fixture_renderer(data, page):
            command = BACKEND / "app" / "previews" / "worker.py"
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",
                str(command),
                str(page),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={
                    key: os.environ[key]
                    for key in ("SystemRoot", "TEMP", "TMP")
                    if key in os.environ
                },
            )
            try:
                output, _ = await asyncio.wait_for(process.communicate(data), 12)
                if process.returncode or len(output) > previews.MAX_OUTPUT:
                    raise RuntimeError("Fixture preview renderer failed")
                return PreviewContent.model_validate_json(output)
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()

        previews.isolated_render = fixture_renderer

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

    async def preview_fixture_loop():
        # Disposable DB/owned provider fixtures only; this does not certify Celery or Redis.
        from app.jobs.preview_queue import tick

        turn = "render"
        while True:
            await tick(async_session_maker, turn=turn)
            turn = "cleanup" if turn == "render" else "render"
            await asyncio.sleep(0.1)

    preview_dispatcher = (
        asyncio.create_task(preview_fixture_loop())
        if os.getenv("TEST_PREVIEW_FIXTURE_RENDERER") == "1"
        else None
    )

    async def scan_fixture_loop():
        # Generated legacy browser fixtures only. Real Phase17 acceptance uses ClamAV
        # and Celery instead; this dependency never bypasses the release gate or hashing.
        from app.core.config import settings
        from app.services.scans import ScanService
        from app.storage.s3 import S3ObjectStorage

        class FixtureScanner:
            async def scan(self, chunks):
                async for _ in chunks:
                    pass
                return "clean", "browser-fixture-dependency"

        while True:
            async with async_session_maker() as db:
                service = ScanService(db, scanner=FixtureScanner())
                job = await service.claim()
                if job:
                    storage = S3ObjectStorage(settings, job.tenant_id)
                    try:
                        service.storage = storage
                        await service.process(job)
                    finally:
                        await storage.close()
            await asyncio.sleep(0.05)

    scan_dispatcher = (
        asyncio.create_task(scan_fixture_loop())
        if os.getenv("TEST_SCAN_FIXTURE") == "1" and os.getenv("TEST_S3_ENDPOINT")
        else None
    )
    try:
        await uvicorn.Server(
            uvicorn.Config(
                "app.main:app",
                host="127.0.0.1",
                port=48000,
                log_level="warning",
                access_log=False,
                ws_max_size=8192,
                ws_max_queue=2,
            )
        ).serve()
    finally:
        if scan_dispatcher:
            scan_dispatcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scan_dispatcher
        dispatcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await dispatcher
        if preview_dispatcher:
            preview_dispatcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await preview_dispatcher
        await engine.dispose()


def main():
    # Real live tests use a separately selected development/test Redis database.
    if os.getenv("TEST_REDIS_URL"):
        os.environ["REDIS_URL"] = os.environ["TEST_REDIS_URL"]
    with tempfile.TemporaryDirectory(prefix="cloudvault-e2e-") as directory:
        os.environ.update(
            {
                "DATABASE_URL": f"sqlite+aiosqlite:///{Path(directory) / 'accounts.db'}",
                "ENVIRONMENT": "development",
                "DEBUG": "false",
                "SECRET_KEY": "cloudvault-disposable-e2e-secret-not-for-production",
                "SMTP_HOST": "127.0.0.1",
                "SMTP_PORT": "41025",
                "SMTP_STARTTLS": "false",
                "SMTP_USERNAME": "",
                "FRONTEND_URL": "http://127.0.0.1:43000",
                "CORS_ORIGINS": '["http://127.0.0.1:43000"]',
            }
        )
        storage_client = None
        test_bucket = None
        if os.environ.get("TEST_S3_ENDPOINT"):
            import boto3
            from botocore.config import Config as S3Config

            test_bucket = "cv-browser-upload-" + uuid4().hex
            storage_client = boto3.client(
                "s3",
                endpoint_url=os.environ["TEST_S3_ENDPOINT"],
                aws_access_key_id=os.environ["TEST_S3_ACCESS_KEY"],
                aws_secret_access_key=os.environ["TEST_S3_SECRET_KEY"],
                region_name="us-east-1",
                config=S3Config(
                    signature_version="s3v4", s3={"addressing_style": "path"}
                ),
            )
            if STORAGE_MANIFEST.exists():
                raise RuntimeError(
                    "Clean up the prior disposable storage test bucket first"
                )
            STORAGE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
            STORAGE_MANIFEST.write_text(
                json.dumps(
                    {"bucket": test_bucket, "endpoint": os.environ["TEST_S3_ENDPOINT"]}
                )
            )
            storage_client.create_bucket(Bucket=test_bucket)
            os.environ.update(
                {
                    "S3_ENDPOINT": os.environ["TEST_S3_ENDPOINT"],
                    "S3_PUBLIC_ENDPOINT": os.environ["TEST_S3_ENDPOINT"],
                    "S3_ACCESS_KEY": os.environ["TEST_S3_ACCESS_KEY"],
                    "S3_SECRET_KEY": os.environ["TEST_S3_SECRET_KEY"],
                    "S3_BUCKET_NAME": test_bucket,
                }
            )
        else:
            # Ordinary account journeys must not inherit an application bucket.
            for name in (
                "S3_ENDPOINT",
                "S3_PUBLIC_ENDPOINT",
                "S3_ACCESS_KEY",
                "S3_SECRET_KEY",
                "S3_BUCKET_NAME",
            ):
                os.environ.pop(name, None)
        from alembic import command
        from alembic.config import Config

        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "migrations"))
        smtp = http = None
        try:
            command.upgrade(config, "head")
            smtp = socketserver.ThreadingTCPServer(("127.0.0.1", 41025), SMTPInbox)
            http = ThreadingHTTPServer(("127.0.0.1", 48025), InboxHTTP)
            for server in (smtp, http):
                threading.Thread(target=server.serve_forever, daemon=True).start()
            asyncio.run(serve())
        finally:
            for server in (smtp, http):
                if server:
                    server.shutdown()
                    server.server_close()
            if storage_client:
                try:
                    cleanup_storage()
                finally:
                    storage_client.close()


def cleanup_storage():
    if not STORAGE_MANIFEST.exists():
        return
    import re

    import boto3
    from botocore.config import Config as S3Config
    from botocore.exceptions import ClientError

    manifest = json.loads(STORAGE_MANIFEST.read_text())
    bucket = manifest["bucket"]
    if not re.fullmatch(r"cv-browser-upload-[0-9a-f]{32}", bucket):
        raise RuntimeError("Refusing to clean an unrecognized storage test bucket")
    if manifest["endpoint"] != os.environ.get("TEST_S3_ENDPOINT"):
        raise RuntimeError("Test storage endpoint changed; refusing cleanup")
    client = boto3.client(
        "s3",
        endpoint_url=manifest["endpoint"],
        aws_access_key_id=os.environ["TEST_S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["TEST_S3_SECRET_KEY"],
        region_name="us-east-1",
        config=S3Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    try:
        try:
            for page in client.get_paginator("list_multipart_uploads").paginate(
                Bucket=bucket
            ):
                for upload in page.get("Uploads", []):
                    client.abort_multipart_upload(
                        Bucket=bucket, Key=upload["Key"], UploadId=upload["UploadId"]
                    )
            for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
                for item in page.get("Contents", []):
                    client.delete_object(Bucket=bucket, Key=item["Key"])
            client.delete_bucket(Bucket=bucket)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "NoSuchBucket":
                raise
        STORAGE_MANIFEST.unlink(missing_ok=True)
    finally:
        client.close()


if __name__ == "__main__":
    if "--cleanup-storage" in sys.argv:
        cleanup_storage()
    else:
        main()
