from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.config import settings
from app.storage.base import ObjectInfo, ObjectNotFoundError, StorageUnavailableError
from tests.api.test_auth import register_user
from tests.api.test_organizations import add_member, bearer
from tests.api.test_uploads import BODY, DIGEST, ROOT, start, storage

# Reuse the actual upload contract fixture; download signing is a unit-test provider boundary.
__all__ = ["storage"]


async def uploaded(client, owner):
    ticket = await start(client, owner)
    id = ticket["file"]["id"]
    assert (await client.post(f"{ROOT}/{id}/complete", headers=bearer(owner))).status_code == 200
    return id


@pytest.mark.asyncio
async def test_download_owner_member_scope_and_pending(client, storage):
    async def sign(ref, name, ttl):
        assert name == "Report.txt" and ttl == 300
        return "https://storage.invalid/download"

    storage.presign_download = sign
    owner = await register_user(client)
    id = await uploaded(client, owner)
    member, _ = await add_member(client, owner)
    response = await client.post(f"{ROOT}/{id}/download-url", headers=bearer(member))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["file"]["checksum_sha256"] == DIGEST
    assert response.json()["expires_at"] and "storage_bucket" not in response.json()["file"]
    outsider = await register_user(client, email="outsider@example.com")
    assert (
        await client.post(f"{ROOT}/{id}/download-url", headers=bearer(outsider))
    ).status_code == 404
    assert (
        await client.post(f"{ROOT}/{uuid4()}/download-url", headers=bearer(owner))
    ).status_code == 404
    pending = await start(client, owner, name="Pending.txt")
    assert (
        await client.post(f"{ROOT}/{pending['file']['id']}/download-url", headers=bearer(owner))
    ).status_code == 409
    assert (await client.post(f"{ROOT}/{id}/download-url")).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,status",
    [(ObjectNotFoundError("private"), 409), (StorageUnavailableError("private"), 503)],
)
async def test_provider_errors_are_safe(client, storage, failure, status):
    owner = await register_user(client)
    id = await uploaded(client, owner)
    storage.error = failure
    result = await client.post(f"{ROOT}/{id}/download-url", headers=bearer(owner))
    assert result.status_code == status and "private" not in result.text


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["size", "checksum", "etag", "type"])
async def test_modified_objects_are_not_downloadable(client, storage, change):
    owner = await register_user(client)
    id = await uploaded(client, owner)
    storage.info = ObjectInfo(
        len(BODY) + int(change == "size"),
        "text/html" if change == "type" else "application/octet-stream",
        '"changed"' if change == "etag" else '"etag"',
        datetime.now(UTC),
        "wrong" if change == "checksum" else DIGEST,
    )
    assert (
        await client.post(f"{ROOT}/{id}/download-url", headers=bearer(owner))
    ).status_code == 409


@pytest.mark.asyncio
async def test_configuration_drift_and_rate_limit(client, storage, monkeypatch):
    owner = await register_user(client)
    id = await uploaded(client, owner)
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "other-bucket")
    for _ in range(10):
        assert (
            await client.post(f"{ROOT}/{id}/download-url", headers=bearer(owner))
        ).status_code == 503
    assert (
        await client.post(f"{ROOT}/{id}/download-url", headers=bearer(owner))
    ).status_code == 429


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["inspection", "signing"])
async def test_revocation_during_storage_inspection_blocks_signing(
    client, db_factory, storage, stage
):
    from datetime import timedelta
    from uuid import UUID

    from sqlalchemy import select

    from app.models import Membership

    owner = await register_user(client)
    id = await uploaded(client, owner)
    signer_called = False

    async def sign(*args):
        nonlocal signer_called
        signer_called = True
        if stage == "signing":
            await revoke()
        return "https://storage.invalid/download"

    async def revoke():
        async with db_factory() as db:
            membership = await db.scalar(
                select(Membership).where(Membership.user_id == UUID(owner["user"]["id"]))
            )
            membership.revoked_at = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()

    async def inspect(ref):
        if stage == "inspection":
            await revoke()
        return storage.info

    storage.presign_download = sign
    storage.inspect_upload = inspect
    assert (
        await client.post(f"{ROOT}/{id}/download-url", headers=bearer(owner))
    ).status_code == 403
    assert signer_called == (stage == "signing")


@pytest.mark.asyncio
async def test_signing_failure_is_safe(client, storage):
    owner = await register_user(client)
    id = await uploaded(client, owner)

    async def sign(*args):
        raise StorageUnavailableError("private-provider-details")

    storage.presign_download = sign
    result = await client.post(f"{ROOT}/{id}/download-url", headers=bearer(owner))
    assert result.status_code == 503 and "private-provider-details" not in result.text
