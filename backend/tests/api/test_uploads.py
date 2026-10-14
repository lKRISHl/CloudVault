import asyncio
import base64
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.storage import get_upload_storage
from app.core.config import settings
from app.main import app
from app.models import File
from app.schemas.uploads import UploadStart
from app.services.auth import AuthService
from app.services.uploads import UploadService
from app.storage.base import ObjectInfo, ObjectNotFoundError, StorageUnavailableError, UploadGrant
from tests.api.test_auth import REGISTER_PAYLOAD, register_user
from tests.api.test_folders import create as create_folder
from tests.api.test_organizations import add_member, bearer

BODY = b"sample"
DIGEST = base64.b64encode(hashlib.sha256(BODY).digest()).decode()
ROOT = "/api/v1/files"


class ContractStorage:
    """Unit-test dependency only; actual provider behavior has separate integration tests."""

    def __init__(self):
        self.info = ObjectInfo(
            len(BODY), "application/octet-stream", '"etag"', datetime.now(UTC), DIGEST
        )
        self.error = None

    async def presign_upload(self, ref, size_bytes, checksum_sha256, expires_seconds):
        if self.error:
            raise self.error
        return UploadGrant("https://storage.invalid/upload", {"If-None-Match": "*"})

    async def inspect_upload(self, ref):
        if self.error:
            raise self.error
        return self.info


@pytest_asyncio.fixture
async def storage(monkeypatch):
    store = ContractStorage()
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "cv-unit-uploads")

    async def override():
        yield store

    app.dependency_overrides[get_upload_storage] = override
    try:
        yield store
    finally:
        app.dependency_overrides.pop(get_upload_storage, None)


def payload(**values):
    return {
        "name": "Report.txt",
        "declared_size_bytes": len(BODY),
        "declared_content_type": "text/plain",
        "checksum_sha256": DIGEST,
        "request_id": str(uuid4()),
        **values,
    }


async def start(client, actor, **values):
    response = await client.post(ROOT + "/uploads", headers=bearer(actor), json=payload(**values))
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


@pytest.mark.asyncio
async def test_upload_reservation_persistence_idempotency_and_completion(
    client, db_factory, storage
):
    owner = await register_user(client)
    data = payload()
    first = await client.post(ROOT + "/uploads", headers=bearer(owner), json=data)
    repeated = await client.post(ROOT + "/uploads", headers=bearer(owner), json=data)
    assert first.status_code == repeated.status_code == 201
    file = first.json()["file"]
    assert repeated.json()["file"]["id"] == file["id"] and file["status"] == "pending"
    assert file["size_bytes"] is None and "object_id" not in file and "storage_bucket" not in file
    conflict = await client.post(
        ROOT + "/uploads", headers=bearer(owner), json={**data, "name": "Changed"}
    )
    assert conflict.status_code == 409
    complete = await client.post(f"{ROOT}/{file['id']}/complete", headers=bearer(owner))
    assert complete.status_code == 200
    verified = complete.json()
    assert verified["status"] == "uploaded" and verified["size_bytes"] == len(BODY)
    assert verified["checksum_sha256"] == DIGEST and verified["completed_at"]
    assert verified["content_type"] == "application/octet-stream"
    replay = await client.post(f"{ROOT}/{file['id']}/complete", headers=bearer(owner))
    assert replay.json()["completed_at"] == verified["completed_at"]
    async with db_factory() as db:
        stored = await db.get(File, UUID(file["id"]))
        assert stored.object_id and stored.storage_bucket == "cv-unit-uploads"
        assert len(list(await db.scalars(select(File)))) == 1


@pytest.mark.asyncio
async def test_upload_permission_parent_and_tenant_boundaries(client, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    foreign = await register_user(client, email="foreign@example.com", tenant_name="Foreign")
    parent = await create_folder(client, owner, "Owner folder")
    other = await create_folder(client, foreign, "Foreign folder")
    assert (
        await client.post(
            ROOT + "/uploads", headers=bearer(member), json=payload(folder_id=parent["id"])
        )
    ).status_code == 403
    assert (
        await client.post(
            ROOT + "/uploads", headers=bearer(owner), json=payload(folder_id=other["id"])
        )
    ).status_code == 404
    ticket = await start(client, owner, folder_id=parent["id"])
    fid = ticket["file"]["id"]
    for actor, status in ((member, 403), (foreign, 404)):
        assert (
            await client.post(f"{ROOT}/{fid}/complete", headers=bearer(actor))
        ).status_code == status
        assert (
            await client.post(
                f"{ROOT}/{fid}/upload-url", headers=bearer(actor), json={"checksum_sha256": DIGEST}
            )
        ).status_code == status
    assert (await client.get(f"{ROOT}/{fid}", headers=bearer(member))).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("size_bytes", 999),
        ("checksum_sha256", None),
        ("checksum_sha256", "wrong"),
        ("content_type", "text/html"),
    ],
)
async def test_completion_never_trusts_mismatched_object_metadata(
    client, db_factory, storage, field, value
):
    from dataclasses import replace

    owner = await register_user(client)
    ticket = await start(client, owner)
    storage.info = replace(storage.info, **{field: value})
    fid = ticket["file"]["id"]
    assert (await client.post(f"{ROOT}/{fid}/complete", headers=bearer(owner))).status_code == 409
    async with db_factory() as db:
        stored = await db.get(File, UUID(fid))
        assert stored.status == "pending" and stored.size_bytes is None


@pytest.mark.asyncio
async def test_retry_deadlines_missing_objects_and_storage_failure(client, db_factory, storage):
    owner = await register_user(client)
    ticket = await start(client, owner)
    fid = ticket["file"]["id"]
    retry = await client.post(
        f"{ROOT}/{fid}/upload-url", headers=bearer(owner), json={"checksum_sha256": DIGEST}
    )
    assert retry.status_code == 200 and retry.json()["file"]["id"] == fid
    wrong = base64.b64encode(b"x" * 32).decode()
    assert (
        await client.post(
            f"{ROOT}/{fid}/upload-url", headers=bearer(owner), json={"checksum_sha256": wrong}
        )
    ).status_code == 409
    for error, code in (
        (ObjectNotFoundError("missing"), 409),
        (StorageUnavailableError("secret"), 503),
    ):
        storage.error = error
        response = await client.post(f"{ROOT}/{fid}/complete", headers=bearer(owner))
        assert response.status_code == code and "secret" not in response.text
    storage.error = None
    async with db_factory() as db:
        stored = await db.get(File, UUID(fid))
        stored.upload_expires_at = datetime.now(UTC) - timedelta(seconds=1000)
        await db.commit()
    assert (
        await client.post(
            f"{ROOT}/{fid}/upload-url", headers=bearer(owner), json={"checksum_sha256": DIGEST}
        )
    ).status_code == 410
    assert (await client.post(f"{ROOT}/{fid}/complete", headers=bearer(owner))).status_code == 410


@pytest.mark.asyncio
async def test_grant_failure_rolls_back_and_size_authentication_validation(
    client, db_factory, storage
):
    assert (await client.post(ROOT + "/uploads", json=payload())).status_code == 401
    pending = (await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)).json()
    assert (
        await client.post(ROOT + "/uploads", headers=bearer(pending), json=payload())
    ).status_code == 403
    owner = await register_user(client, email="verified-upload@example.com", tenant_name="Owner")
    assert (
        await client.post(
            ROOT + "/uploads",
            headers=bearer(owner),
            json=payload(declared_size_bytes=settings.UPLOAD_MAX_BYTES + 1),
        )
    ).status_code == 413
    for values in (
        {"checksum_sha256": "bad"},
        {"status": "uploaded"},
        {"tenant_id": str(uuid4())},
        {"object_id": str(uuid4())},
    ):
        assert (
            await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload(**values))
        ).status_code == 422
    storage.error = StorageUnavailableError("private-provider-message")
    assert (
        await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload())
    ).status_code == 503
    async with db_factory() as db:
        assert list(await db.scalars(select(File))) == []


@pytest.mark.asyncio
async def test_concurrent_start_and_completion_keep_one_identity(client, db_factory, storage):
    owner = await register_user(client)
    data = UploadStart(**payload())

    async def initiate():
        async with db_factory() as db:
            actor = await AuthService(db).get_user_in_tenant(
                UUID(owner["user"]["id"]), UUID(owner["user"]["tenant"]["id"])
            )
            return await UploadService(db, storage).start(actor, data)

    first, second = await asyncio.gather(initiate(), initiate())
    assert first.file.id == second.file.id

    async def complete():
        async with db_factory() as db:
            actor = await AuthService(db).get_user_in_tenant(
                UUID(owner["user"]["id"]), UUID(owner["user"]["tenant"]["id"])
            )
            return await UploadService(db, storage).complete(actor, first.file.id)

    first_done, second_done = await asyncio.gather(complete(), complete())
    assert first_done.completed_at == second_done.completed_at


@pytest.mark.asyncio
async def test_grant_rate_limit(client, storage, monkeypatch):
    owner = await register_user(client)
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX", 1)
    ticket = await start(client, owner)
    assert (
        await client.post(
            f"{ROOT}/{ticket['file']['id']}/upload-url",
            headers=bearer(owner),
            json={"checksum_sha256": DIGEST},
        )
    ).status_code == 429


@pytest.mark.asyncio
async def test_uploaded_constraint_blocks_forged_verified_fields(client, db_factory, storage):
    owner = await register_user(client)
    ticket = await start(client, owner)
    fid = UUID(ticket["file"]["id"])
    async with db_factory() as db:
        file = await db.get(File, fid)
        file.status = "uploaded"
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
    assert (await client.post(f"{ROOT}/{fid}/complete", headers=bearer(owner))).status_code == 200
    async with db_factory() as db:
        file = await db.get(File, fid)
        file.content_type = None
        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.asyncio
async def test_completion_rechecks_parent_authority_and_revoked_membership(client, storage):
    owner = await register_user(client)
    admin, _ = await add_member(client, owner, "uploader@example.com", "admin")
    folder = await create_folder(client, owner, "Owner documents")
    ticket = await start(client, admin, folder_id=folder["id"])
    uid = admin["user"]["id"]
    assert (
        await client.patch(
            f"/api/v1/organizations/current/members/{uid}",
            headers=bearer(owner),
            json={"role": "member"},
        )
    ).status_code == 200
    endpoint = f"{ROOT}/{ticket['file']['id']}/complete"
    assert (await client.post(endpoint, headers=bearer(admin))).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/organizations/current/members/{uid}",
            headers=bearer(owner),
            json={"role": "admin"},
        )
    ).status_code == 200
    assert (await client.post(endpoint, headers=bearer(admin))).status_code == 200
    assert (
        await client.delete(f"/api/v1/organizations/current/members/{uid}", headers=bearer(owner))
    ).status_code == 204
    assert (await client.post(endpoint, headers=bearer(admin))).status_code == 401


@pytest.mark.asyncio
async def test_unconfigured_uploads_fail_without_creating_metadata(client, db_factory, monkeypatch):
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", None)
    owner = await register_user(client)
    config = (await client.get(ROOT + "/upload-configuration", headers=bearer(owner))).json()
    assert not config["enabled"]
    assert (
        await client.post(ROOT + "/uploads", headers=bearer(owner), json=payload())
    ).status_code == 503
    async with db_factory() as db:
        assert list(await db.scalars(select(File))) == []
