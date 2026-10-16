"""Real API/provider/Redis/prefork/ClamAV acceptance inside an owned test container.

Requires an explicitly named cv_phase17_live_* disposable database and matching bucket.
Never run against application data. The caller owns database/bucket/container teardown.
"""

import asyncio
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
from app.core.config import settings
from app.core.database import async_session_maker, engine
from app.jobs.tasks import scan_maintenance
from app.main import app
from app.models import FileVersion
from app.models.account import EmailOutbox
from app.services.email import mail_cipher
from app.storage.s3 import S3ObjectStorage
from sqlalchemy import select


async def main():
    from sqlalchemy.engine import make_url

    database = make_url(settings.DATABASE_URL).database
    if not re.fullmatch(r"cv_phase17_live_[0-9a-f]{12}", database or ""):
        raise RuntimeError("Refusing unowned acceptance database")
    if settings.S3_BUCKET_NAME != database.replace("_", "-"):
        raise RuntimeError("Refusing unowned acceptance bucket")
    await asyncio.to_thread(
        subprocess.run, [sys.executable, "-m", "alembic", "upgrade", "head"], check=True
    )
    store = S3ObjectStorage(settings, UUID(int=0))
    await store.call(store.client.create_bucket)
    queue = database
    worker = None
    server = None
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as api:
            account = await api.post(
                "/api/v1/auth/register",
                json={
                    "email": database + "@example.com",
                    "password": "correct-horse-battery",
                    "full_name": "Scan acceptance",
                    "tenant_name": database,
                },
            )
            assert account.status_code == 201, account.text
            headers = {"Authorization": "Bearer " + account.json()["access_token"]}
            async with async_session_maker() as db:
                mail = await db.scalar(
                    select(EmailOutbox).where(EmailOutbox.purpose == "verify")
                )
                payload = json.loads(
                    mail_cipher().decrypt(mail.encrypted_payload.encode())
                )
                link = next(
                    line
                    for line in payload["body"].splitlines()
                    if line.startswith("http")
                )
                token = parse_qs(urlsplit(link).fragment)["token"][0]
            assert (
                await api.post("/api/v1/account/verify", json={"token": token})
            ).status_code == 200

            async def upload(body, name):
                ticket = await api.post(
                    "/api/v1/files/uploads",
                    headers=headers,
                    json={
                        "name": name,
                        "declared_size_bytes": len(body),
                        "request_id": str(uuid4()),
                        "checksum_sha256": base64.b64encode(
                            hashlib.sha256(body).digest()
                        ).decode(),
                    },
                )
                assert ticket.status_code == 201, ticket.text
                ticket = ticket.json()
                async with httpx.AsyncClient() as provider:
                    put = await provider.put(
                        ticket["upload_url"], headers=ticket["headers"], content=body
                    )
                    assert put.status_code == 200, put.text
                fid = ticket["file"]["id"]
                completed = await api.post(
                    f"/api/v1/files/{fid}/complete", headers=headers
                )
                assert completed.status_code == 200, completed.text
                assert completed.json()["scan_status"] == "pending"
                return fid

            clean = await upload(b"CloudVault actual verified scan", "clean.txt")
            # Decode only inside Linux RAM. The harmless antivirus fixture is never a host file.
            eicar = base64.b64decode(
                "WDVPIVAlQEFQWzRcUFpYNTQoUF4pN0NDKTd9JEVJQ0FSLVNUQU5EQVJELUFOVElWSVJVUy1URVNULUZJTEUhJEgrSCo="
            )
            blocked = await upload(eicar, "detection-test.txt")
            for fid in (clean, blocked):
                assert (
                    await api.post(f"/api/v1/files/{fid}/download-url", headers=headers)
                ).status_code == 423
                assert (
                    await api.post(
                        f"/api/v1/files/{fid}/shares",
                        headers=headers,
                        json={"expires_in_hours": 1, "allow_download": True},
                    )
                ).status_code == 423
            print(
                "Actual API quarantine rejects download and share before worker start",
                flush=True,
            )
            worker = await asyncio.to_thread(
                subprocess.Popen,
                [
                    "celery",
                    "-A",
                    "app.jobs.celery_app:celery_app",
                    "worker",
                    "--loglevel=ERROR",
                    "--pool=prefork",
                    "--concurrency=1",
                    "--queues=" + queue,
                    "--hostname=phase17@%h",
                    "--without-gossip",
                    "--without-mingle",
                ],
            )
            for expected_file, expected_state in (
                (clean, "clean"),
                (blocked, "blocked"),
            ):
                scan_maintenance.apply_async(queue=queue)
                for _ in range(120):
                    async with async_session_maker() as db:
                        states = {
                            str(row.file_id): row.scan_status
                            for row in (await db.scalars(select(FileVersion))).all()
                        }
                    # Claim ordering is fair by UUID, so either object may scan first.
                    if states.get(expected_file) == expected_state:
                        break
                    if "pending" in states.values():
                        scan_maintenance.apply_async(queue=queue)
                    await asyncio.sleep(1)
                else:
                    raise AssertionError(
                        f"Real queue did not reach expected state: {states}"
                    )
            grant = await api.post(
                f"/api/v1/files/{clean}/download-url", headers=headers
            )
            assert grant.status_code == 200, grant.text
            async with httpx.AsyncClient() as provider:
                result = await provider.get(grant.json()["download_url"])
                assert result.content == b"CloudVault actual verified scan"
            assert (
                await api.post(f"/api/v1/files/{blocked}/download-url", headers=headers)
            ).status_code == 423
            assert (
                await api.post(
                    f"/api/v1/files/{blocked}/preview", headers=headers, json={}
                )
            ).status_code == 423
            assert (
                await api.post(
                    f"/api/v1/files/{blocked}/preview-jobs",
                    headers=headers,
                    json={"request_id": str(uuid4())},
                )
            ).status_code == 423
            print(
                "Real PostgreSQL/API/S3/Redis/prefork/ClamAV clean release and EICAR quarantine passed",
                flush=True,
            )
            if os.getenv("PHASE17_BROWSER") == "1":
                # Only an owned fixture directory is shared with the host, never app data.
                evidence = Path("/evidence")
                server = await asyncio.to_thread(
                    subprocess.Popen,
                    [
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        "8000",
                        "--log-level",
                        "warning",
                        "--no-access-log",
                    ],
                )
                (evidence / "fixture.json").write_text(
                    json.dumps(
                        {
                            "email": database + "@example.com",
                            "password": "correct-horse-battery",
                            "clean": clean,
                            "blocked": blocked,
                        }
                    )
                )
                print("Owned browser fixture ready", flush=True)
                for _ in range(240):
                    if (evidence / "done").exists():
                        break
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError("Owned browser acceptance deadline exceeded")
    finally:
        if server:
            server.terminate()
            await asyncio.to_thread(server.wait, timeout=15)
        if worker:
            worker.terminate()
            try:
                worker.wait(timeout=15)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
        try:
            result = await store.call(store.client.list_objects_v2)
            for item in result.get("Contents", []):
                await store.call(store.client.delete_object, Key=item["Key"])
            await store.call(store.client.delete_bucket)
        finally:
            await store.close()
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
