import asyncio
import base64
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models import File, FileVersion
from app.scanning.clamd import ClamdScanner, ScannerUnavailableError
from app.services.scans import ScanService, fingerprint, policy, require_released
from app.storage.base import ObjectInfo
from tests.api.test_auth import register_user
from tests.api.test_organizations import bearer
from tests.api.test_previews import PreviewStore, complete

pytestmark = [pytest.mark.asyncio, pytest.mark.scan_enforcement]


class ScanStore(PreviewStore):
    async def presign_download(self, ref, name, ttl):
        return "https://storage.invalid/released-download"

    async def stream_for_scanning(self, ref, etag, size):
        for offset in range(0, len(self.body), 2):
            yield self.body[offset : offset + 2]


class Scanner:
    def __init__(self, verdict="clean", callback=None):
        self.verdict, self.callback = verdict, callback

    async def scan(self, chunks):
        async for _ in chunks:
            pass
        if self.callback:
            await self.callback()
        if self.verdict == "error":
            raise ScannerUnavailableError("Private scanner response")
        return self.verdict, "1.5/1234"


async def uploaded(client, db_factory, monkeypatch, body=b"scan exact bytes"):
    from app.api.storage import get_upload_storage
    from app.main import app

    owner = await register_user(client)
    store = ScanStore()
    store.body = body
    store.info = ObjectInfo(
        len(body),
        "application/octet-stream",
        '"verified"',
        datetime.now(UTC),
        base64.b64encode(hashlib.sha256(body).digest()).decode(),
    )
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "scan-test")

    async def dependency():
        yield store

    app.dependency_overrides[get_upload_storage] = dependency
    file_id = UUID(await complete(client, owner, store))
    async with db_factory() as db:
        version_id = await db.scalar(select(FileVersion.id).where(FileVersion.file_id == file_id))
    return owner, store, file_id, version_id


async def run_scan(db_factory, store, scanner=None):
    async with db_factory() as db:
        service = ScanService(db, store, scanner or Scanner())
        job = await service.claim()
        assert job
        return await service.process(job)


async def test_queue_waits_for_scanner_without_spending_upload_attempts(
    client, db_factory, monkeypatch
):
    from app.jobs.scan_queue import tick

    owner, store, fid, vid = await uploaded(client, db_factory, monkeypatch)

    async def unavailable(self):
        raise ScannerUnavailableError("Scanner unavailable or definitions stale")

    monkeypatch.setattr(ClamdScanner, "version", unavailable)
    # Three failed dependency probes must not permanently exhaust the uploaded version.
    for _ in range(3):
        with pytest.raises(ScannerUnavailableError):
            await tick(db_factory)
    async with db_factory() as db:
        version = await db.get(FileVersion, vid)
        assert version.scan_status == "pending"
        assert version.scan_attempts == 0
        assert version.scan_lease_id is None
    assert (await client.post(
        f"/api/v1/files/{fid}/download-url", headers=bearer(owner)
    )).status_code == 423

    async def ready(self):
        return "1.5/1234"

    async def close():
        pass

    async def scan(self, chunks):
        return await Scanner().scan(chunks)

    monkeypatch.setattr(ClamdScanner, "version", ready)
    monkeypatch.setattr(ClamdScanner, "scan", scan)
    monkeypatch.setattr("app.jobs.scan_queue.S3ObjectStorage", lambda *_: store)
    monkeypatch.setattr(store, "close", close, raising=False)
    assert await tick(db_factory) == "clean"
    async with db_factory() as db:
        version = await db.get(FileVersion, vid)
        assert version.scan_attempts == 1
        assert (await require_released(db, await db.get(File, fid))).id == vid


async def test_quarantine_blocks_all_grant_surfaces_then_clean_scan_releases(
    client, db_factory, monkeypatch
):
    owner, store, fid, vid = await uploaded(client, db_factory, monkeypatch)
    headers = bearer(owner)
    for path, payload in [
        (f"/files/{fid}/download-url", None),
        (f"/files/{fid}/versions/{vid}/download-url", None),
        (f"/files/{fid}/preview", {}),
        (f"/files/{fid}/preview-jobs", {"request_id": str(uuid4())}),
        (f"/files/{fid}/shares", {"expires_in_hours": 1, "allow_download": True}),
    ]:
        response = await client.post("/api/v1" + path, headers=headers, json=payload)
        assert response.status_code == 423, (path, response.text)
    assert await run_scan(db_factory, store) == "clean"
    async with db_factory() as db:
        file = await db.get(File, fid)
        version = await require_released(db, file)
        assert file.scan_status == version.scan_status == "clean"
        assert version.scan_fingerprint == fingerprint(version) and version.scan_policy == policy()
    assert (
        await client.post(f"/api/v1/files/{fid}/download-url", headers=headers)
    ).status_code == 200


@pytest.mark.parametrize("verdict", ["blocked", "error"])
async def test_blocked_and_scanner_errors_never_release(client, db_factory, monkeypatch, verdict):
    owner, store, fid, _ = await uploaded(client, db_factory, monkeypatch)
    assert await run_scan(db_factory, store, Scanner(verdict)) == verdict
    async with db_factory() as db:
        with pytest.raises(HTTPException) as failure:
            await require_released(db, await db.get(File, fid))
        assert failure.value.status_code == 423
    assert (
        await client.post(f"/api/v1/files/{fid}/download-url", headers=bearer(owner))
    ).status_code == 423


async def test_source_hash_mismatch_and_oversize_fail_closed(client, db_factory, monkeypatch):
    _, store, fid, vid = await uploaded(client, db_factory, monkeypatch)
    store.body = b"wrong same size!"
    assert await run_scan(db_factory, store) == "error"
    async with db_factory() as db:
        version = await db.get(FileVersion, vid)
        version.scan_status, version.scan_next_attempt_at = "pending", None
        version.size_bytes = version.declared_size_bytes = settings.SCAN_MAX_BYTES + 1
        await db.commit()
    assert await run_scan(db_factory, store) == "oversized"


async def test_duplicate_claim_and_expired_owner_cannot_publish(client, db_factory, monkeypatch):
    owner, store, fid, vid = await uploaded(client, db_factory, monkeypatch)
    async with db_factory() as db:
        first = await ScanService(db, store, Scanner()).claim()
    assert (
        await client.post(f"/api/v1/files/{fid}/versions/{vid}/scan", headers=bearer(owner))
    ).status_code == 409
    async with db_factory() as db:
        assert await ScanService(db).claim() is None
        row = await db.get(FileVersion, vid)
        row.scan_lease_until = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    async with db_factory() as db:
        second = await ScanService(db, store, Scanner()).claim()
        assert second.scan_lease_id != first.scan_lease_id
        assert await ScanService(db, store, Scanner()).process(first) == "superseded"
        assert await ScanService(db, store, Scanner()).process(second) == "clean"


async def test_pruning_during_scan_prevents_clean_publication(client, db_factory, monkeypatch):
    _, store, _, vid = await uploaded(client, db_factory, monkeypatch)

    async def prune():
        async with db_factory() as db:
            version = await db.get(FileVersion, vid)
            version.prune_requested_at = version.prune_not_before = datetime.now(UTC)
            await db.commit()

    assert await run_scan(db_factory, store, Scanner(callback=prune)) == "error"


async def test_clean_verdict_cannot_follow_changed_metadata_or_policy(
    client, db_factory, monkeypatch
):
    _, store, fid, vid = await uploaded(client, db_factory, monkeypatch)
    assert await run_scan(db_factory, store) == "clean"
    async with db_factory() as db:
        version = await db.get(FileVersion, vid)
        version.storage_etag = '"changed"'
        await db.commit()
        with pytest.raises(HTTPException):
            await require_released(db, await db.get(File, fid))


async def test_clamd_real_protocol_framing_freshness_and_error_sanitization(monkeypatch):
    received = bytearray()

    async def peer(reader, writer):
        command = await reader.readuntil(b"\0")
        if command == b"zVERSION\0":
            stamp = datetime.now(UTC).strftime("%a %b %d %H:%M:%S %Y")
            writer.write(f"ClamAV 1.5/1234/{stamp}\0".encode())
        else:
            assert command == b"zINSTREAM\0"
            while length := int.from_bytes(await reader.readexactly(4), "big"):
                received.extend(await reader.readexactly(length))
            writer.write(b"stream: OK\0")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(peer, "127.0.0.1", 0)
    monkeypatch.setattr(settings, "CLAMD_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "CLAMD_PORT", server.sockets[0].getsockname()[1])

    async def chunks():
        yield b"owned bytes"

    try:
        assert await ClamdScanner().scan(chunks()) == ("clean", "1.5/1234")
        assert received == b"owned bytes"
    finally:
        server.close()
        await server.wait_closed()


async def test_scanner_cannot_release_without_consuming_verified_bytes(
    client, db_factory, monkeypatch
):
    _, store, _, _ = await uploaded(client, db_factory, monkeypatch)

    class SkippingScanner:
        async def scan(self, chunks):
            return "clean", "1.5/1234"

    assert await run_scan(db_factory, store, SkippingScanner()) == "error"


async def test_changed_policy_automatically_rescans_clean_version(client, db_factory, monkeypatch):
    _, store, fid, _ = await uploaded(client, db_factory, monkeypatch)
    assert await run_scan(db_factory, store) == "clean"
    monkeypatch.setattr(settings, "SCAN_MAX_BYTES", settings.SCAN_MAX_BYTES - 1)
    async with db_factory() as db:
        with pytest.raises(HTTPException):
            await require_released(db, await db.get(File, fid))
    # A policy change must not leave clean-labelled versions permanently stranded.
    async with db_factory() as db:
        row = await db.scalar(select(FileVersion).where(FileVersion.file_id == fid))
        row.scan_next_attempt_at = None
        await db.commit()
    assert await run_scan(db_factory, store) == "clean"


async def test_retry_requires_owner_scope_and_does_not_override_blocked(
    client, db_factory, monkeypatch
):
    owner, store, fid, vid = await uploaded(client, db_factory, monkeypatch)
    assert await run_scan(db_factory, store, Scanner("error")) == "error"
    outsider = await register_user(client, email="outsider-scans@example.com")
    path = f"/api/v1/files/{fid}/versions/{vid}/scan"
    assert (await client.post(path, headers=bearer(outsider))).status_code == 404
    assert (await client.post(path, headers=bearer(owner))).status_code == 202
    assert await run_scan(db_factory, store, Scanner("blocked")) == "blocked"
    assert (await client.post(path, headers=bearer(owner))).status_code == 409


@pytest.mark.parametrize("body", [b"", b"a", b"scan empty and nonempty"])
async def test_exact_empty_and_basic_content_release(client, db_factory, monkeypatch, body):
    _, store, fid, _ = await uploaded(client, db_factory, monkeypatch, body)
    assert await run_scan(db_factory, store) == "clean"
    async with db_factory() as db:
        await require_released(db, await db.get(File, fid))


@pytest.mark.parametrize(
    "version_reply", [b"bad\0", b"ClamAV 1.5/1/Thu Jan 01 00:00:00 1970\0", b"x" * 3000 + b"\0"]
)
async def test_unusable_definitions_and_protocol_replies_fail_closed(monkeypatch, version_reply):
    async def peer(reader, writer):
        await reader.readuntil(b"\0")
        writer.write(version_reply)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(peer, "127.0.0.1", 0)
    monkeypatch.setattr(settings, "CLAMD_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "CLAMD_PORT", server.sockets[0].getsockname()[1])
    try:
        with pytest.raises(
            ScannerUnavailableError, match="Scanner unavailable or definitions stale"
        ):
            await ClamdScanner().version()
    finally:
        server.close()
        await server.wait_closed()


async def test_scan_attempts_are_bounded_then_manual_retry_resets(client, db_factory, monkeypatch):
    owner, store, fid, vid = await uploaded(client, db_factory, monkeypatch)
    for attempt in range(3):
        assert await run_scan(db_factory, store, Scanner("error")) == "error"
        async with db_factory() as db:
            row = await db.get(FileVersion, vid)
            assert row.scan_attempts == attempt + 1
            row.scan_next_attempt_at = None
            await db.commit()
    async with db_factory() as db:
        assert await ScanService(db).claim() is None
    assert (
        await client.post(f"/api/v1/files/{fid}/versions/{vid}/scan", headers=bearer(owner))
    ).status_code == 202
    assert await run_scan(db_factory, store) == "clean"


async def test_composite_stream_rehashes_part_boundaries_and_rejects_bad_digest(
    client, db_factory, monkeypatch
):
    _, store, _, _ = await uploaded(client, db_factory, monkeypatch, b"parts cross read boundaries")
    async with db_factory() as db:
        job = await ScanService(db).claim()
        job.checksum_kind = "sha256-composite"
        job.multipart_part_size = 3
        pieces = [store.body[i : i + 3] for i in range(0, len(store.body), 3)]
        job.multipart_count = len(pieces)
        composite = hashlib.sha256(
            b"".join(hashlib.sha256(piece).digest() for piece in pieces)
        ).digest()
        job.checksum_sha256 = job.expected_checksum_sha256 = base64.b64encode(composite).decode()
        store.info = ObjectInfo(
            len(store.body),
            "application/octet-stream",
            job.storage_etag,
            datetime.now(UTC),
            f"{job.checksum_sha256}-{job.multipart_count}",
        )
        assert (
            b"".join([chunk async for chunk in ScanService(db, store).verified_chunks(job)])
            == store.body
        )
        store.body = b"x" * len(store.body)
        from app.storage.base import StorageError

        with pytest.raises(StorageError, match="checksum changed"):
            _ = [chunk async for chunk in ScanService(db, store).verified_chunks(job)]


async def test_existing_anonymous_share_stops_resolving_after_release_invalidates(
    client, db_factory, monkeypatch
):
    owner, store, fid, vid = await uploaded(client, db_factory, monkeypatch)
    assert await run_scan(db_factory, store) == "clean"
    response = await client.post(
        f"/api/v1/files/{fid}/shares",
        headers=bearer(owner),
        json={"expires_in_hours": 1, "allow_download": True},
    )
    assert response.status_code == 201, response.text
    token = response.json()["share_url"].split("#token=")[1]
    response = await client.post("/api/v1/shares/access", json={"token": token})
    assert response.status_code == 200, response.text
    async with db_factory() as db:
        row = await db.get(FileVersion, vid)
        row.scan_status = "error"
        await db.commit()
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 404


async def test_operator_health_reports_failed_scans_and_unavailable_definitions(
    client, db_factory, monkeypatch
):
    from app.jobs import check_jobs
    from app.services.background_jobs import BackgroundJobService

    _, store, _, _ = await uploaded(client, db_factory, monkeypatch)
    assert await run_scan(db_factory, store, Scanner("error")) == "error"
    monkeypatch.setattr(
        settings, "DATABASE_URL", db_factory.kw["bind"].url.render_as_string(hide_password=False)
    )

    async def healthy_dispatch(cursor):
        return None

    async def healthy_storage():
        return "ok"

    monkeypatch.setattr(check_jobs, "storage_dependency", healthy_storage)

    await BackgroundJobService(db_factory).run("scans", healthy_dispatch)
    result = (await check_jobs.inspect(["scans"]))[0]
    assert result["state"] == "degraded"
    assert result["backlog"]["failed_scans"]["count"] == 1

    async def unavailable(self):
        raise ScannerUnavailableError("Private signature/provider detail")

    monkeypatch.setattr(ClamdScanner, "version", unavailable)
    result = (await check_jobs.inspect(["scans"], probe_scanner=True))[0]
    assert result["state"] == "dependency_unavailable"
    assert result["scanner_dependency"] == "unavailable_or_stale"
    assert "Private" not in str(result)


async def test_ready_cached_preview_cannot_outlive_source_release(client, db_factory, monkeypatch):
    from app.models import PreviewJob

    owner, store, fid, vid = await uploaded(client, db_factory, monkeypatch)
    assert await run_scan(db_factory, store) == "clean"
    response = await client.post(
        f"/api/v1/files/{fid}/preview-jobs",
        headers=bearer(owner),
        json={"request_id": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    async with db_factory() as db:
        job = await db.get(PreviewJob, UUID(job_id))
        job.state = "ready"
        # Unsupported output has no derivative bytes to put into the database.
        job.metadata_json = {"kind": "unsupported", "reason": "Generated unsupported fixture"}
        await db.commit()
    path = f"/api/v1/files/{fid}/preview-jobs/{job_id}"
    assert (await client.get(path, headers=bearer(owner))).status_code == 200
    async with db_factory() as db:
        version = await db.get(FileVersion, vid)
        version.scan_status = "error"
        await db.commit()
    response = await client.get(path, headers=bearer(owner))
    assert response.status_code == 423
    assert "Generated unsupported fixture" not in response.text
