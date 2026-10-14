import base64
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.api.storage import get_upload_storage
from app.core.config import settings
from app.main import app
from app.models import File, UploadPart
from app.storage.base import (
    ObjectInfo,
    ObjectNotFoundError,
    StorageUnavailableError,
    StoredPart,
    UploadGrant,
)
from tests.api.test_auth import register_user
from tests.api.test_organizations import add_member, bearer

ROOT = "/api/v1/files"
PART = 5 * 1024 * 1024
HASHES = [base64.b64encode(hashlib.sha256(value).digest()).decode() for value in [b"first", b"end"]]


class ContractMultipart:
    """Unit boundary only. Actual S3 bytes/checksums are verified in integration tests."""

    def __init__(self):
        self.receipts = {}
        self.objects = {}
        self.created = []
        self.aborted = []
        self.error = None
        self.lost_ack = False

    async def create_multipart(self, ref):
        if self.error:
            raise self.error
        self.created.append(ref)
        return "provider-upload-" + str(ref.file_id)

    async def presign_part(self, ref, upload_id, number, size, checksum, ttl):
        if self.error:
            raise self.error
        return UploadGrant("https://storage.invalid/part", {"x-amz-checksum-sha256": checksum})

    async def inspect_part(self, ref, upload_id, number):
        if self.error:
            raise self.error
        if (ref.file_id, number) not in self.receipts:
            raise ObjectNotFoundError("missing")
        return self.receipts[(ref.file_id, number)]

    async def list_parts(self, ref, upload_id):
        if self.error:
            raise self.error
        return [
            part
            for (file_id, _), part in sorted(self.receipts.items(), key=lambda entry: entry[0][1])
            if file_id == ref.file_id
        ]

    async def inspect_upload(self, ref):
        if self.error:
            raise self.error
        if ref.file_id not in self.objects:
            raise ObjectNotFoundError("missing")
        return self.objects[ref.file_id]

    async def complete_multipart(self, ref, upload_id, parts):
        digest = base64.b64encode(
            hashlib.sha256(
                b"".join(base64.b64decode(part.checksum_sha256) for part in parts)
            ).digest()
        ).decode()
        self.objects[ref.file_id] = ObjectInfo(
            sum(part.size_bytes for part in parts),
            "application/octet-stream",
            '"object-etag"',
            datetime.now(UTC),
            digest + "-" + str(len(parts)),
        )
        if self.lost_ack:
            raise StorageUnavailableError("ambiguous acknowledgement")

    async def abort_multipart(self, ref, upload_id):
        self.aborted.append(ref.file_id)
        self.receipts = {
            key: value for key, value in self.receipts.items() if key[0] != ref.file_id
        }

    def received(self, ticket):
        for part in ticket["parts"]:
            self.receipts[(UUID(ticket["file"]["id"]), part["number"])] = StoredPart(
                part["number"],
                part["size_bytes"],
                '"part-' + str(part["number"]) + '"',
                part["checksum_sha256"],
            )


@pytest_asyncio.fixture
async def storage(monkeypatch):
    store = ContractMultipart()
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "cv-unit-multipart")
    monkeypatch.setattr(settings, "MULTIPART_PART_BYTES", PART)

    async def override():
        yield store

    app.dependency_overrides[get_upload_storage] = override
    try:
        yield store
    finally:
        app.dependency_overrides.pop(get_upload_storage, None)


def payload(**values):
    return {
        "name": "Chunks.bin",
        "declared_size_bytes": PART + 3,
        "declared_content_type": "application/octet-stream",
        "part_size": PART,
        "checksums": HASHES,
        "request_id": str(uuid4()),
        **values,
    }


async def start(client, actor, **values):
    result = await client.post(
        ROOT + "/multipart/uploads", headers=bearer(actor), json=payload(**values)
    )
    assert result.status_code == 201, result.text
    assert result.headers["cache-control"] == "no-store"
    return result.json()


@pytest.mark.asyncio
async def test_parts_receipts_completion_and_reconciliation(client, db_factory, storage):
    owner = await register_user(client)
    data = payload()
    first = await client.post(ROOT + "/multipart/uploads", headers=bearer(owner), json=data)
    ticket = first.json()
    id = ticket["file"]["id"]
    repeat = await client.post(ROOT + "/multipart/uploads", headers=bearer(owner), json=data)
    assert repeat.json()["file"]["id"] == id and len(storage.created) == 1
    assert (
        ticket["file"]["upload_method"] == "multipart"
        and "multipart_upload_id" not in ticket["file"]
    )
    assert (
        await client.post(f"{ROOT}/{id}/multipart/complete", headers=bearer(owner))
    ).status_code == 409
    assert (await client.post(f"{ROOT}/{id}/complete", headers=bearer(owner))).status_code == 409
    storage.received(ticket)
    for number in [1, 2]:
        result = await client.post(
            f"{ROOT}/{id}/multipart/parts/{number}/confirm", headers=bearer(owner)
        )
        assert result.status_code == 200 and result.json()["confirmed"]
    storage.lost_ack = True
    completed = await client.post(f"{ROOT}/{id}/multipart/complete", headers=bearer(owner))
    assert completed.status_code == 200, completed.text
    assert (
        completed.json()["status"] == "uploaded"
        and completed.json()["checksum_kind"] == "sha256-composite"
    )
    assert (
        completed.json()["multipart_state"] == "completed"
        and len(completed.json()["checksum_sha256"]) == 44
    )
    again = await client.post(f"{ROOT}/{id}/multipart/complete", headers=bearer(owner))
    assert again.json()["completed_at"] == completed.json()["completed_at"]
    assert (
        await client.post(f"{ROOT}/{id}/multipart/abort", headers=bearer(owner))
    ).status_code == 409
    async with db_factory() as db:
        assert (await db.get(UploadPart, (UUID(id), 1))).confirmed_at


@pytest.mark.asyncio
async def test_scope_creator_conflicts_and_cancel(client, storage):
    owner = await register_user(client)
    ticket = await start(client, owner)
    id = ticket["file"]["id"]
    outsider = await register_user(client, email="outsider@example.com")
    member, _ = await add_member(client, owner)
    for endpoint in ["complete", "abort", "parts/1/url", "parts/1/confirm"]:
        assert (
            await client.post(f"{ROOT}/{id}/multipart/{endpoint}", headers=bearer(outsider))
        ).status_code == 404
        assert (
            await client.post(f"{ROOT}/{id}/multipart/{endpoint}", headers=bearer(member))
        ).status_code == 403
    assert (
        await client.post(f"{ROOT}/{id}/multipart/parts/3/url", headers=bearer(owner))
    ).status_code == 404
    assert (
        await client.post(f"{ROOT}/{id}/multipart/parts/0/url", headers=bearer(owner))
    ).status_code == 422
    storage.received(ticket)
    aborted = await client.post(f"{ROOT}/{id}/multipart/abort", headers=bearer(owner))
    assert aborted.status_code == 200 and aborted.json()["multipart_state"] == "aborted"
    assert (
        await client.post(f"{ROOT}/{id}/multipart/abort", headers=bearer(owner))
    ).status_code == 200
    assert (
        await client.post(f"{ROOT}/{id}/multipart/complete", headers=bearer(owner))
    ).status_code == 409
    assert storage.aborted == [UUID(id)]


@pytest.mark.asyncio
async def test_expiry_mismatch_and_provider_errors(client, db_factory, storage):
    owner = await register_user(client)
    ticket = await start(client, owner)
    id = ticket["file"]["id"]
    storage.received(ticket)
    storage.receipts[(UUID(id), 1)] = StoredPart(1, PART, '"etag"', HASHES[1])
    assert (
        await client.post(f"{ROOT}/{id}/multipart/parts/1/confirm", headers=bearer(owner))
    ).status_code == 409
    assert (
        await client.post(f"{ROOT}/{id}/multipart/complete", headers=bearer(owner))
    ).status_code == 409
    storage.error = StorageUnavailableError("private provider detail")
    error = await client.post(f"{ROOT}/{id}/multipart/parts/1/url", headers=bearer(owner))
    assert error.status_code == 503 and "private" not in error.text
    storage.error = None
    async with db_factory() as db:
        file = await db.get(File, UUID(id))
        file.upload_expires_at = datetime.now(UTC) - timedelta(hours=1)
        await db.commit()
    assert (
        await client.post(f"{ROOT}/{id}/multipart/parts/1/url", headers=bearer(owner))
    ).status_code == 410
    assert (
        await client.post(f"{ROOT}/{id}/multipart/complete", headers=bearer(owner))
    ).status_code == 410
    assert (
        await client.post(f"{ROOT}/{id}/multipart/abort", headers=bearer(owner))
    ).status_code == 200


@pytest.mark.asyncio
async def test_bad_plans_idempotency_and_rollback(client, db_factory, storage):
    owner = await register_user(client)
    for change in [
        {"checksums": ["bad"]},
        {"checksums": HASHES[:1]},
        {"declared_size_bytes": 0},
        {"part_size": True},
        {"declared_size_bytes": settings.MULTIPART_MAX_BYTES + 1},
    ]:
        assert (
            await client.post(
                ROOT + "/multipart/uploads", headers=bearer(owner), json=payload(**change)
            )
        ).status_code in [413, 422]
    data = payload()
    ticket = await client.post(ROOT + "/multipart/uploads", headers=bearer(owner), json=data)
    assert ticket.status_code == 201
    assert (
        await client.post(
            ROOT + "/multipart/uploads", headers=bearer(owner), json={**data, "name": "changed"}
        )
    ).status_code == 409
    storage.error = StorageUnavailableError("private")
    failure = await client.post(
        ROOT + "/multipart/uploads", headers=bearer(owner), json=payload(name="Failure.bin")
    )
    assert failure.status_code == 503
    async with db_factory() as db:
        from sqlalchemy import select

        assert await db.scalar(select(File.id).where(File.name == "Failure.bin")) is None


@pytest.mark.asyncio
async def test_initialization_signing_failure_aborts_provider_and_rolls_back(
    client, db_factory, storage
):
    from sqlalchemy import select

    owner = await register_user(client)

    async def broken_grant(*args):
        raise StorageUnavailableError("private signing detail")

    storage.presign_part = broken_grant
    failed = await client.post(ROOT + "/multipart/uploads", headers=bearer(owner), json=payload())
    assert failed.status_code == 503 and "private" not in failed.text
    assert len(storage.aborted) == 1
    async with db_factory() as db:
        assert await db.scalar(select(File.id)) is None
        assert await db.scalar(select(UploadPart.file_id)) is None


@pytest.mark.asyncio
async def test_parent_authority_and_revoked_membership_are_rechecked(client, storage):
    from tests.api.test_folders import create

    owner = await register_user(client)
    folder = await create(client, owner, "Owner folder")
    admin, _ = await add_member(client, owner, role="admin")
    ticket = await start(client, admin, folder_id=folder["id"])
    id = ticket["file"]["id"]
    storage.received(ticket)
    changed = await client.patch(
        "/api/v1/organizations/current/members/" + admin["user"]["id"],
        headers=bearer(owner),
        json={"role": "member"},
    )
    assert changed.status_code == 200, changed.text
    assert (
        await client.post(f"{ROOT}/{id}/multipart/parts/1/url", headers=bearer(admin))
    ).status_code == 403
    assert (
        await client.post(f"{ROOT}/{id}/multipart/complete", headers=bearer(admin))
    ).status_code == 403
    assert (
        await client.delete(
            "/api/v1/organizations/current/members/" + admin["user"]["id"], headers=bearer(owner)
        )
    ).status_code == 204
    assert (
        await client.post(f"{ROOT}/{id}/multipart/abort", headers=bearer(admin))
    ).status_code in [401, 403]


@pytest.mark.asyncio
async def test_part_grants_remain_bounded_without_basic_ten_request_limit(client, storage):
    owner = await register_user(client)
    ticket = await start(client, owner)
    id = ticket["file"]["id"]
    for _ in range(12):
        result = await client.post(f"{ROOT}/{id}/multipart/parts/1/url", headers=bearer(owner))
        assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    changed = await client.post(
        ROOT + "/multipart/uploads",
        headers=bearer(owner),
        json=payload(request_id=ticket["file"]["id"]),
    )
    assert changed.status_code == 409
