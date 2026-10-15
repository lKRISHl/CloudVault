import asyncio
import base64
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api.storage import get_upload_storage
from app.core.config import settings
from app.main import app
from app.models import FileVersion, VersionPart
from app.services.version_cleanup import VersionCleanupService
from app.storage.base import (
    MultipartNotFoundError,
    ObjectInfo,
    ObjectNotFoundError,
    StorageError,
    StoredPart,
    UploadGrant,
)
from tests.api.test_auth import register_user
from tests.api.test_downloads import uploaded
from tests.api.test_organizations import add_member, bearer
from tests.api.test_versions import declaration

PART = 5 * 1024 * 1024


class VersionStore:
    """Fault injection boundary; real bytes use the provider integration suite."""

    def __init__(self):
        self.client = SimpleNamespace(get_bucket_versioning=object())
        self.objects, self.uploads, self.parts = {}, {}, {}
        self.fail_create = self.fail_complete = self.fail_delete = False
        self.serial = 0
        self.bucket_versioning = None

    async def call(self, operation):
        return {"Status": self.bucket_versioning} if self.bucket_versioning else {}

    async def presign_upload(self, ref, size, checksum, ttl):
        self.objects[ref.object_id] = ObjectInfo(
            size, "application/octet-stream", '"basic"', datetime.now(UTC), checksum
        )
        return UploadGrant("https://storage.invalid/upload", {"If-None-Match": "*"})

    async def inspect_upload(self, ref):
        if ref.object_id not in self.objects:
            raise ObjectNotFoundError("missing")
        return self.objects[ref.object_id]

    async def presign_download(self, ref, name, ttl):
        return "https://storage.invalid/" + str(ref.object_id)

    async def create_multipart(self, ref):
        self.serial += 1
        upload = "upload-" + str(self.serial)
        self.uploads.setdefault(ref.object_id, set()).add(upload)
        if self.fail_create:
            self.fail_create = False
            raise StorageError("lost create acknowledgement")
        return upload

    async def pending_for_object(self, ref):
        return list(self.uploads.get(ref.object_id, set()))

    async def abort_multipart(self, ref, upload_id):
        self.uploads.get(ref.object_id, set()).discard(upload_id)

    async def presign_part(self, ref, upload_id, number, size, checksum, ttl):
        return UploadGrant("https://storage.invalid/part", {"x-amz-checksum-sha256": checksum})

    async def list_parts(self, ref, upload_id):
        if upload_id not in self.uploads.get(ref.object_id, set()):
            raise MultipartNotFoundError("missing")
        return [
            value
            for (oid, _), value in sorted(self.parts.items(), key=lambda pair: pair[0][1])
            if oid == ref.object_id
        ]

    async def inspect_part(self, ref, upload_id, number):
        part = self.parts.get((ref.object_id, number))
        if part is None:
            raise ObjectNotFoundError("missing")
        return part

    async def complete_multipart(self, ref, upload_id, parts):
        digest = base64.b64encode(
            hashlib.sha256(b"".join(base64.b64decode(p.checksum_sha256) for p in parts)).digest()
        ).decode()
        self.objects[ref.object_id] = ObjectInfo(
            sum(p.size_bytes for p in parts),
            "application/octet-stream",
            '"multipart"',
            datetime.now(UTC),
            digest + "-" + str(len(parts)),
        )
        await self.abort_multipart(ref, upload_id)
        if self.fail_complete:
            raise StorageError("lost complete acknowledgement")

    async def delete(self, ref):
        if self.fail_delete:
            raise StorageError("delete unavailable")
        self.objects.pop(ref.object_id, None)


@pytest_asyncio.fixture
async def storage(monkeypatch):
    store = VersionStore()
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "cv-version-transfers")
    monkeypatch.setattr(settings, "MULTIPART_PART_BYTES", PART)

    async def dependency():
        yield store

    app.dependency_overrides[get_upload_storage] = dependency
    yield store
    app.dependency_overrides.pop(get_upload_storage, None)


def manifest(generation=1):
    hashes = [
        base64.b64encode(hashlib.sha256(chunk).digest()).decode() for chunk in [b"first", b"tail"]
    ]
    checksum = base64.b64encode(
        hashlib.sha256(b"".join(base64.b64decode(h) for h in hashes)).digest()
    ).decode()
    return {
        **declaration(generation, declared_size_bytes=PART + 4, checksum_sha256=checksum),
        "checksums": hashes,
        "part_size": PART,
    }


async def begin(client, actor, fid, payload=None):
    response = await client.post(
        f"/api/v1/files/{fid}/versions/multipart", headers=bearer(actor), json=payload or manifest()
    )
    assert response.status_code == 201, response.text
    return response.json()


async def receive(db_factory, store, vid, numbers=(1, 2)):
    async with db_factory() as db:
        version = await db.get(FileVersion, UUID(vid))
        for part in await db.scalars(
            select(VersionPart).where(VersionPart.version_id == version.id)
        ):
            if part.number in numbers:
                store.parts[version.object_id, part.number] = StoredPart(
                    part.number, part.size_bytes, f'"part-{part.number}"', part.checksum_sha256
                )


@pytest.mark.asyncio
async def test_multipart_resume_missing_parts_lost_completion_and_stale_grants(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    payload = manifest()
    ticket = await begin(client, owner, fid, payload)
    vid = ticket["version"]["id"]
    root = f"/api/v1/files/{fid}/versions/{vid}"
    await receive(db_factory, storage, vid, (1,))
    assert (await client.post(root + "/parts/1/confirm", headers=bearer(owner))).status_code == 200
    progress = (await client.get(root + "/progress", headers=bearer(owner))).json()
    assert progress["confirmed_bytes"] == PART and all(
        not part["upload_url"] for part in progress["parts"]
    )
    resumed = await client.post(
        root + "/resume", headers=bearer(owner), json={"checksums": payload["checksums"]}
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["parts"][0]["confirmed"] and not resumed.json()["parts"][0]["upload_url"]
    assert resumed.json()["parts"][1]["upload_url"]
    assert resumed.json()["expires_at"] == ticket["expires_at"]
    await receive(db_factory, storage, vid)
    storage.fail_complete = True
    completed = await client.post(root + "/complete", headers=bearer(owner))
    assert completed.status_code == 200, completed.text
    assert (
        completed.json()["current_version"] == 2
        and completed.json()["checksum_kind"] == "sha256-composite"
    )
    assert (await client.post(root + "/complete", headers=bearer(owner))).json()[
        "version_generation"
    ] == 2
    assert (await client.post(root + "/parts/1/url", headers=bearer(owner))).status_code == 409


@pytest.mark.asyncio
async def test_unknown_initialization_ack_has_durable_exact_reference_and_cancellation(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    payload = manifest()
    storage.fail_create = True
    response = await client.post(
        f"/api/v1/files/{fid}/versions/multipart", headers=bearer(owner), json=payload
    )
    assert response.status_code == 503
    async with db_factory() as db:
        version = await db.scalar(select(FileVersion).where(FileVersion.number == 2))
        assert version.multipart_state == "initializing" and version.multipart_upload_id is None
        assert len(list(await db.scalars(select(VersionPart)))) == 2
        oid = version.object_id
    assert len(storage.uploads[oid]) == 1
    ticket = await begin(client, owner, fid, payload)
    assert len(storage.uploads[oid]) == 1 and storage.serial == 2
    root = f"/api/v1/files/{fid}/versions/{ticket['version']['id']}"
    assert (await client.post(root + "/cancel", headers=bearer(owner))).status_code == 202
    assert not storage.uploads[oid]
    for suffix in ["/complete", "/parts/1/url", "/parts/1/confirm"]:
        assert (await client.post(root + suffix, headers=bearer(owner))).status_code == 410
    assert (await client.get(f"/api/v1/files/{fid}", headers=bearer(owner))).json()[
        "current_version"
    ] == 1


@pytest.mark.asyncio
async def test_superseded_candidate_cancels_and_cleans_without_touching_versions(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    ticket = await begin(client, owner, fid)
    basic = (
        await client.post(
            f"/api/v1/files/{fid}/versions", headers=bearer(owner), json=declaration()
        )
    ).json()
    assert (
        await client.post(
            f"/api/v1/files/{fid}/versions/{basic['version']['id']}/complete", headers=bearer(owner)
        )
    ).status_code == 200
    vid = ticket["version"]["id"]
    root = f"/api/v1/files/{fid}/versions/{vid}"
    assert (await client.post(root + "/parts/1/url", headers=bearer(owner))).status_code == 409
    assert (await client.post(root + "/cancel", headers=bearer(owner))).status_code == 202
    async with db_factory() as db:
        row = await db.get(FileVersion, UUID(vid))
        tenant, version_id = row.tenant_id, row.id
        await db.rollback()
        assert not await VersionCleanupService(db, storage).sweep(version_id, tenant)
        assert await VersionCleanupService(db, storage).sweep(
            version_id, tenant, datetime.now(UTC) + timedelta(days=1)
        )
        assert (await db.get(FileVersion, version_id)).cleaned_at
    assert len(storage.objects) == 2


@pytest.mark.asyncio
async def test_prune_authority_download_window_counting_failure_and_current_protection(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    member, _ = await add_member(client, owner)
    await client.put(
        f"/api/v1/files/{fid}/permissions/{member['user']['id']}",
        headers=bearer(owner),
        json={"role": "editor"},
    )
    first = (await client.get(f"/api/v1/files/{fid}/versions", headers=bearer(owner))).json()[
        "items"
    ][0]
    basic = (
        await client.post(
            f"/api/v1/files/{fid}/versions", headers=bearer(owner), json=declaration()
        )
    ).json()
    await client.post(
        f"/api/v1/files/{fid}/versions/{basic['version']['id']}/complete", headers=bearer(owner)
    )
    root = f"/api/v1/files/{fid}/versions/{first['id']}"
    assert (
        await client.post(root + "/prune", headers=bearer(member), json={"confirmation": "DELETE"})
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/files/{fid}/versions/{basic['version']['id']}/prune",
            headers=bearer(owner),
            json={"confirmation": "DELETE"},
        )
    ).status_code == 409
    before = (await client.get(f"/api/v1/files/{fid}/versions", headers=bearer(owner))).json()[
        "retained_bytes"
    ]
    assert (
        await client.post(root + "/prune", headers=bearer(owner), json={"confirmation": "DELETE"})
    ).status_code == 202
    assert (await client.post(root + "/download-url", headers=bearer(owner))).status_code == 404
    assert (
        await client.post(root + "/restore", headers=bearer(owner), json={"base_generation": 2})
    ).status_code == 404
    assert (await client.get(f"/api/v1/files/{fid}/versions", headers=bearer(owner))).json()[
        "retained_bytes"
    ] == before
    async with db_factory() as db:
        row = await db.get(FileVersion, UUID(first["id"]))
        later = row.prune_not_before.replace(tzinfo=UTC) + timedelta(seconds=1)
        vid, tenant = row.id, row.tenant_id
        await db.rollback()
        assert not await VersionCleanupService(db, storage).sweep(vid, tenant)
        storage.fail_delete = True
        assert not await VersionCleanupService(db, storage).sweep(vid, tenant, later)
        assert (await db.get(FileVersion, vid)).purged_at is None
        await db.rollback()
        storage.fail_delete = False
        assert await VersionCleanupService(db, storage).sweep(vid, tenant, later)
    assert (await client.get(f"/api/v1/files/{fid}/versions", headers=bearer(owner))).json()[
        "retained_bytes"
    ] == before - first["size_bytes"]


@pytest.mark.asyncio
async def test_retention_keeps_newest_plus_restored_current_and_is_irreversible(client, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    root = f"/api/v1/files/{fid}"
    initial = (await client.get(root + "/versions", headers=bearer(owner))).json()["items"][0]
    for generation in [1, 2]:
        ticket = (
            await client.post(
                root + "/versions", headers=bearer(owner), json=declaration(generation)
            )
        ).json()
        assert (
            await client.post(
                root + f"/versions/{ticket['version']['id']}/complete", headers=bearer(owner)
            )
        ).status_code == 200
    assert (
        await client.post(
            root + f"/versions/{initial['id']}/restore",
            headers=bearer(owner),
            json={"base_generation": 3},
        )
    ).status_code == 200
    result = await client.put(
        root + "/version-policy",
        headers=bearer(owner),
        json={"keep_last": 1, "confirmation": "PRUNE"},
    )
    assert result.status_code == 200, result.text
    rows = (await client.get(root + "/versions", headers=bearer(owner))).json()["items"]
    assert [r["number"] for r in rows if r["prune_requested_at"]] == [2]
    assert next(r for r in rows if r["number"] == 1)["is_current"]
    fresh = (
        await client.post(root + "/versions", headers=bearer(owner), json=declaration(4))
    ).json()
    assert (
        await client.post(
            root + f"/versions/{fresh['version']['id']}/complete", headers=bearer(owner)
        )
    ).status_code == 200
    after_activation = (await client.get(root + "/versions", headers=bearer(owner))).json()["items"]
    assert {row["number"] for row in after_activation if row["prune_requested_at"]} == {1, 2, 3}
    assert after_activation[0]["is_current"] and not after_activation[0]["prune_requested_at"]
    await client.put(
        root + "/version-policy",
        headers=bearer(owner),
        json={"keep_last": None, "confirmation": "PRUNE"},
    )
    assert next(
        r
        for r in (await client.get(root + "/versions", headers=bearer(owner))).json()["items"]
        if r["number"] == 2
    )["prune_requested_at"]


@pytest.mark.asyncio
async def test_restore_prune_race_has_one_safe_winner(client, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    root = f"/api/v1/files/{fid}"
    initial = (await client.get(root + "/versions", headers=bearer(owner))).json()["items"][0]
    version = (
        await client.post(root + "/versions", headers=bearer(owner), json=declaration())
    ).json()
    await client.post(
        root + f"/versions/{version['version']['id']}/complete", headers=bearer(owner)
    )
    a, b = await asyncio.gather(
        client.post(
            root + f"/versions/{initial['id']}/restore",
            headers=bearer(owner),
            json={"base_generation": 2},
        ),
        client.post(
            root + f"/versions/{initial['id']}/prune",
            headers=bearer(owner),
            json={"confirmation": "DELETE"},
        ),
    )
    assert (a.status_code, b.status_code) in [(200, 409), (404, 202)]


@pytest.mark.asyncio
async def test_multipart_revoked_private_authority_blocks_every_candidate_operation(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    member, _ = await add_member(client, owner)
    foreign = await register_user(client, email="version-transfer-foreign@example.com")
    root = f"/api/v1/files/{fid}"
    await client.patch(root + "/permissions", headers=bearer(owner), json={"visibility": "private"})
    grant = root + f"/permissions/{member['user']['id']}"
    assert (
        await client.put(grant, headers=bearer(owner), json={"role": "editor"})
    ).status_code == 204
    ticket = await begin(client, member, fid)
    vid = ticket["version"]["id"]
    await receive(db_factory, storage, vid)
    candidate = root + f"/versions/{vid}"
    assert (await client.post(candidate + "/complete", headers=bearer(owner))).status_code == 403
    assert (await client.get(candidate + "/progress", headers=bearer(foreign))).status_code == 404
    assert (await client.put(grant, headers=bearer(owner), json={"role": None})).status_code == 204
    for path, body in [
        ("/resume", {"checksums": manifest()["checksums"]}),
        ("/parts/1/url", None),
        ("/parts/1/confirm", None),
        ("/complete", None),
        ("/cancel", None),
    ]:
        assert (
            await client.post(candidate + path, headers=bearer(member), json=body)
        ).status_code == 404
    assert (await client.get(candidate + "/progress", headers=bearer(member))).status_code == 404
    assert (await client.get(root, headers=bearer(owner))).json()["current_version"] == 1


@pytest.mark.asyncio
async def test_multipart_cancel_complete_race_has_one_durable_outcome(client, db_factory, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    ticket = await begin(client, owner, fid)
    vid = ticket["version"]["id"]
    await receive(db_factory, storage, vid)
    root = f"/api/v1/files/{fid}/versions/{vid}"
    cancel, complete = await asyncio.gather(
        client.post(root + "/cancel", headers=bearer(owner)),
        client.post(root + "/complete", headers=bearer(owner)),
    )
    assert (cancel.status_code, complete.status_code) in [(202, 410), (409, 200)]
    async with db_factory() as db:
        row = await db.get(FileVersion, UUID(vid))
        assert (row.cancelled_at is not None) == (row.status == "pending")
    current = (await client.get(f"/api/v1/files/{fid}", headers=bearer(owner))).json()
    assert current["current_version"] == (1 if cancel.status_code == 202 else 2)
