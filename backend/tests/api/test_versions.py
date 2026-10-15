import asyncio
import base64
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models import File, FileVersion, FileVersionChange, TrashEntry
from app.services.trash_cleanup import TrashCleanupService
from app.services.version_cleanup import VersionCleanupService
from app.storage.base import ObjectInfo, StorageError
from tests.api.test_auth import register_user
from tests.api.test_downloads import uploaded
from tests.api.test_organizations import add_member, bearer
from tests.api.test_shares import create as share
from tests.api.test_trash import trash
from tests.api.test_uploads import BODY, DIGEST, storage
from tests.test_trash_cleanup import PurgeStore

__all__ = ["storage"]


@pytest.mark.asyncio
async def test_history_pages_and_retained_accounting_include_older_versions(
    client, db_factory, storage
):
    from app.models.file_version import CONTENT_FIELDS

    owner = await register_user(client)
    fid = await uploaded(client, owner)
    async with db_factory() as db:
        initial = await db.scalar(select(FileVersion).where(FileVersion.file_id == UUID(fid)))
        for number in range(2, 29):
            values = {key: getattr(initial, key) for key in CONTENT_FIELDS}
            values["object_id"] = uuid4()
            db.add(
                FileVersion(
                    tenant_id=initial.tenant_id,
                    file_id=initial.file_id,
                    number=number,
                    created_by=initial.created_by,
                    request_id=uuid4(),
                    base_generation=1,
                    status="uploaded",
                    **values,
                )
            )
        await db.commit()
    page = await history(client, owner, fid)
    assert len(page["items"]) == 25 and page["has_more"]
    assert page["retained_bytes"] == 28 * len(BODY)
    last = await history(client, owner, fid, 25)
    assert [item["number"] for item in last["items"]] == [3, 2, 1] and not last["has_more"]
    assert last["items"][-1]["is_current"]
    assert (
        await client.get(f"/api/v1/files/{fid}/versions?offset=10001", headers=bearer(owner))
    ).status_code == 422


def declaration(generation=1, body=b"replacement", **values):
    return {
        "request_id": str(uuid4()),
        "base_generation": generation,
        "declared_size_bytes": len(body),
        "declared_content_type": "text/plain",
        "checksum_sha256": base64.b64encode(hashlib.sha256(body).digest()).decode(),
        **values,
    }


async def reserve(client, owner, fid, payload=None):
    result = await client.post(
        f"/api/v1/files/{fid}/versions", headers=bearer(owner), json=payload or declaration()
    )
    assert result.status_code == 201, result.text
    return result.json()


async def finish(client, owner, fid, vid):
    return await client.post(f"/api/v1/files/{fid}/versions/{vid}/complete", headers=bearer(owner))


def replacement(storage, payload):
    storage.info = ObjectInfo(
        payload["declared_size_bytes"],
        "application/octet-stream",
        '"new-etag"',
        datetime.now(UTC),
        payload["checksum_sha256"],
    )


async def history(client, owner, fid, offset=0):
    result = await client.get(
        f"/api/v1/files/{fid}/versions?offset={offset}", headers=bearer(owner)
    )
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    return result.json()


@pytest.mark.asyncio
async def test_versions_keep_original_bytes_restore_and_revoke_external_links(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    original_info = storage.info
    initial = (await history(client, owner, fid))["items"][0]
    _, token = await share(client, owner, fid)
    payload = declaration()
    ticket = await reserve(client, owner, fid, payload)
    assert "object_id" not in ticket["version"] and ticket["version"]["number"] == 2
    assert (await reserve(client, owner, fid, payload))["version"]["id"] == ticket["version"]["id"]
    replacement(storage, payload)
    completed = await finish(client, owner, fid, ticket["version"]["id"])
    assert completed.status_code == 200, completed.text
    assert completed.json()["current_version"] == 2 and completed.json()["version_generation"] == 2
    repeated = await reserve(client, owner, fid, payload)
    assert repeated["upload_url"] is None
    assert (await finish(client, owner, fid, ticket["version"]["id"])).json()[
        "version_generation"
    ] == 2
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 404
    listing = await history(client, owner, fid)
    assert (
        listing["retained_bytes"] == len(BODY) + payload["declared_size_bytes"]
        and listing["pending_bytes"] == 0
    )
    assert [row["is_current"] for row in listing["items"]] == [True, False]

    async def sign(ref, name, ttl):
        return "https://storage.invalid/" + str(ref.object_id)

    storage.presign_download = sign
    storage.info = original_info
    url = f"/api/v1/files/{fid}/versions/{initial['id']}"
    assert (await client.post(url + "/download-url", headers=bearer(owner))).status_code == 200
    restored = await client.post(
        url + "/restore", headers=bearer(owner), json={"base_generation": 2}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["current_version"] == 1 and restored.json()["version_generation"] == 3
    assert restored.json()["checksum_sha256"] == DIGEST
    assert (await history(client, owner, fid))["retained_bytes"] == listing["retained_bytes"]
    # Original transfer APIs must never reinterpret a versioned logical file as an old session.
    assert (
        await client.post(f"/api/v1/files/{fid}/complete", headers=bearer(owner))
    ).status_code == 409
    async with db_factory() as db:
        changes = list(
            await db.scalars(select(FileVersionChange).order_by(FileVersionChange.generation))
        )
        assert [item.reason for item in changes] == ["upload", "restore"]
        versions = list(await db.scalars(select(FileVersion)))
        assert len(versions) == 2 and len({v.object_id for v in versions}) == 2


@pytest.mark.asyncio
async def test_version_tenant_private_viewer_editor_and_trash_boundaries(client, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    member, _ = await add_member(client, owner)
    foreign = await register_user(client, email="version-foreign@example.com")
    assert (
        await client.get(f"/api/v1/files/{fid}/versions", headers=bearer(foreign))
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/files/{fid}/versions", headers=bearer(member), json=declaration()
        )
    ).status_code == 403
    await client.patch(
        f"/api/v1/files/{fid}/permissions", headers=bearer(owner), json={"visibility": "private"}
    )
    assert (
        await client.get(f"/api/v1/files/{fid}/versions", headers=bearer(member))
    ).status_code == 404
    target = member["user"]["id"]
    grant = f"/api/v1/files/{fid}/permissions/{target}"
    assert (
        await client.put(grant, headers=bearer(owner), json={"role": "editor"})
    ).status_code == 204
    payload = declaration()
    ticket = await reserve(client, member, fid, payload)
    assert (await finish(client, owner, fid, ticket["version"]["id"])).status_code == 403
    replacement(storage, payload)
    assert (await finish(client, member, fid, ticket["version"]["id"])).status_code == 200
    await trash(client, owner, "files", fid)
    assert (
        await client.get(f"/api/v1/files/{fid}/versions", headers=bearer(owner))
    ).status_code == 404
    assert (await finish(client, member, fid, ticket["version"]["id"])).status_code == 404


@pytest.mark.asyncio
async def test_stale_concurrent_versions_never_overwrite_new_current_and_cleanup_retries(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    payload = declaration()
    a = await reserve(client, owner, fid, payload)
    b = await reserve(client, owner, fid)
    replacement(storage, payload)
    results = await asyncio.gather(
        finish(client, owner, fid, a["version"]["id"]),
        finish(client, owner, fid, b["version"]["id"]),
    )
    assert sorted(result.status_code for result in results) == [200, 409]
    stale = b if results[1].status_code == 409 else a
    assert (
        await client.post(
            f"/api/v1/files/{fid}/versions", headers=bearer(owner), json=declaration()
        )
    ).status_code == 409
    provider = PurgeStore()
    async with db_factory() as db:
        row = await db.get(FileVersion, UUID(stale["version"]["id"]))
        tenant, vid = row.tenant_id, row.id
        await db.rollback()
        assert not await VersionCleanupService(db, provider).sweep(vid, tenant)
        later = datetime.now(UTC) + timedelta(days=1)
        provider.fail = True
        assert not await VersionCleanupService(db, provider).sweep(vid, tenant, later)
        provider.fail = False
        assert await VersionCleanupService(db, provider).sweep(vid, tenant, later)
        provider.present = True
        assert await VersionCleanupService(db, provider).sweep(
            vid, tenant, later + timedelta(minutes=1)
        )
        assert provider.deleted == 2
    listing = await history(client, owner, fid)
    assert listing["pending_bytes"] == 0 and len(listing["items"]) == 2


@pytest.mark.asyncio
async def test_all_versions_and_pending_refs_purged_with_file_after_latest_deadline(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    payload = declaration()
    ticket = await reserve(client, owner, fid, payload)
    replacement(storage, payload)
    assert (await finish(client, owner, fid, ticket["version"]["id"])).status_code == 200
    await reserve(client, owner, fid, declaration(2))
    entry = await trash(client, owner, "files", fid)
    await client.post(
        f"/api/v1/trash/{entry['id']}/purge", headers=bearer(owner), json={"confirmation": "DELETE"}
    )
    provider = PurgeStore()
    async with db_factory() as db:
        row = await db.get(TrashEntry, UUID(entry["id"]))
        later = row.not_before.replace(tzinfo=UTC) + timedelta(days=1)
        tenant, eid = row.tenant_id, row.id
        await db.rollback()
        assert await TrashCleanupService(db, provider).sweep(eid, tenant, later)
        rows = list(await db.scalars(select(FileVersion).where(FileVersion.file_id == UUID(fid))))
        assert len(rows) == 3 and all(
            v.purged_at if v.status == "uploaded" else v.cleaned_at for v in rows
        )
        assert provider.deleted == 3 and (await db.get(File, UUID(fid))).object_purged_at


@pytest.mark.asyncio
async def test_version_limits_proof_expiry_and_provider_errors_are_safe(
    client, db_factory, storage, monkeypatch
):
    from app.core.config import settings

    owner = await register_user(client)
    fid = await uploaded(client, owner)
    monkeypatch.setattr(settings, "UPLOAD_MAX_BYTES", 20)
    root = f"/api/v1/files/{fid}/versions"
    assert (
        await client.post(root, headers=bearer(owner), json=declaration(declared_size_bytes=21))
    ).status_code == 413
    assert (
        await client.post(root, headers=bearer(owner), json=declaration(checksum_sha256="bad"))
    ).status_code == 422
    payload = declaration()
    ticket = await reserve(client, owner, fid, payload)
    assert (await finish(client, owner, fid, ticket["version"]["id"])).status_code == 409
    storage.error = StorageError("secret-provider-detail")
    result = await finish(client, owner, fid, ticket["version"]["id"])
    assert result.status_code == 503 and "secret" not in result.text
    storage.error = None
    async with db_factory() as db:
        row = await db.get(FileVersion, UUID(ticket["version"]["id"]))
        row.upload_expires_at = datetime.now(UTC) - timedelta(days=1)
        await db.commit()
    assert (await finish(client, owner, fid, ticket["version"]["id"])).status_code == 410
    assert (await client.post(root, headers=bearer(owner), json=payload)).status_code == 410
