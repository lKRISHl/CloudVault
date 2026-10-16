import base64
import hashlib
from datetime import UTC, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api.storage import get_upload_storage
from app.main import app
from app.models import File, FileVersion
from app.storage.base import ObjectInfo, StorageUnavailableError, UploadGrant
from tests.api.test_auth import register_user
from tests.api.test_organizations import add_member, bearer
from tests.api.test_trash import trash
from tests.api.test_uploads import payload
from tests.test_preview_renderer import image_bytes


class PreviewStore:
    def __init__(self):
        self.body = b"Hello <script>window.shouldNeverRun=true</script>"
        self.reads = 0
        self.after_read = None
        self.corrupt = False

    async def presign_upload(self, ref, size, checksum, ttl):
        self.info = ObjectInfo(
            size, "application/octet-stream", '"preview"', datetime.now(UTC), checksum
        )
        return UploadGrant("https://storage.invalid/upload", {})

    async def inspect_upload(self, ref):
        return self.info

    async def read_for_processing(self, ref, maximum):
        self.reads += 1
        if self.after_read:
            await self.after_read()
        return b"changed" if self.corrupt else self.body


@pytest_asyncio.fixture
async def storage(monkeypatch):
    from app.core.config import settings
    from app.previews.worker import render
    from app.schemas.previews import PreviewContent

    store = PreviewStore()
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "cv-preview-unit")

    async def dependency():
        yield store

    async def renderer(data, page):
        return PreviewContent.model_validate(render(data, page))

    monkeypatch.setattr("app.services.previews.isolated_render", renderer)
    app.dependency_overrides[get_upload_storage] = dependency
    yield store
    app.dependency_overrides.pop(get_upload_storage, None)


async def complete(client, actor, store):
    data = payload(
        declared_size_bytes=len(store.body),
        checksum_sha256=base64.b64encode(hashlib.sha256(store.body).digest()).decode(),
        declared_content_type="image/png",
    )  # Deliberately wrong: declaration never establishes type.
    response = await client.post("/api/v1/files/uploads", headers=bearer(actor), json=data)
    assert response.status_code == 201, response.text
    fid = response.json()["file"]["id"]
    assert (
        await client.post(f"/api/v1/files/{fid}/complete", headers=bearer(actor))
    ).status_code == 200
    return fid


async def preview(client, actor, fid, **values):
    return await client.post(f"/api/v1/files/{fid}/preview", headers=bearer(actor), json=values)


@pytest.mark.asyncio
async def test_text_ignores_declared_mime_binds_version_and_has_safe_headers(client, storage):
    owner = await register_user(client)
    fid = await complete(client, owner, storage)
    response = await preview(client, owner, fid)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["kind"] == "text" and result["text"] == storage.body.decode()
    assert (
        result["detected_type"] == "text/plain; charset=utf-8"
        and result["scan_status"] == "unscanned"
    )
    assert result["version_number"] == 1 and result["file_id"] == fid
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in response.headers["content-security-policy"]


@pytest.mark.asyncio
@pytest.mark.parametrize("format", ["PNG", "PDF"])
async def test_native_preview_response_contains_only_sanitized_png(client, storage, format):
    owner = await register_user(client)
    storage.body = image_bytes(format)
    fid = await complete(client, owner, storage)
    response = await preview(client, owner, fid)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["kind"] == ("pdf" if format == "PDF" else "image")
    assert base64.b64decode(result["image_base64"]).startswith(b"\x89PNG\r\n\x1a\n")
    assert "upload_url" not in result and "storage_bucket" not in result


@pytest.mark.asyncio
async def test_foreign_private_trash_pending_and_pruned_versions_never_preview(
    client, db_factory, storage
):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    foreign = await register_user(client, email="preview-foreign@example.com")
    fid = await complete(client, owner, storage)
    assert (await preview(client, foreign, fid)).status_code == 404
    await client.patch(
        f"/api/v1/files/{fid}/permissions", headers=bearer(owner), json={"visibility": "private"}
    )
    assert (await preview(client, member, fid)).status_code == 404
    async with db_factory() as db:
        version = await db.scalar(select(FileVersion).where(FileVersion.file_id == UUID(fid)))
        vid = str(version.id)
        version.prune_requested_at = version.prune_not_before = datetime.now(UTC)
        await db.commit()
    assert (await preview(client, owner, fid, version_id=vid)).status_code == 404
    await trash(client, owner, "files", fid)
    assert (await preview(client, owner, fid)).status_code == 404


@pytest.mark.asyncio
async def test_full_checksum_rejects_changed_bytes_even_when_head_is_unchanged(client, storage):
    owner = await register_user(client)
    fid = await complete(client, owner, storage)
    storage.corrupt = True
    assert (await preview(client, owner, fid)).status_code == 409


@pytest.mark.asyncio
async def test_access_and_current_generation_rechecked_after_provider_read(
    client, db_factory, storage
):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    fid = await complete(client, owner, storage)

    async def revoke():
        await client.patch(
            f"/api/v1/files/{fid}/permissions",
            headers=bearer(owner),
            json={"visibility": "private"},
        )

    storage.after_read = revoke
    assert (await preview(client, member, fid)).status_code == 404

    async def transition():
        async with db_factory() as db:
            file = await db.get(File, UUID(fid))
            file.version_generation += 1
            await db.commit()

    storage.after_read = transition
    assert (await preview(client, owner, fid)).status_code == 409


@pytest.mark.asyncio
async def test_oversized_sources_do_not_read_or_parse_and_bad_pages_are_rejected(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await complete(client, owner, storage)
    async with db_factory() as db:
        file = await db.get(File, UUID(fid))
        version = await db.scalar(select(FileVersion).where(FileVersion.file_id == file.id))
        file.declared_size_bytes = file.size_bytes = version.declared_size_bytes = (
            version.size_bytes
        ) = 10 * 1024 * 1024 + 1
        await db.commit()
    response = await preview(client, owner, fid)
    assert response.status_code == 200 and response.json()["kind"] == "unsupported"
    assert storage.reads == 0
    assert (await preview(client, owner, fid, page=-1)).status_code == 422
    assert (await preview(client, owner, fid, page=100)).status_code == 422


@pytest.mark.asyncio
async def test_pending_candidates_and_storage_failures_never_return_content(client, storage):
    from tests.api.test_versions import reserve

    owner = await register_user(client)
    fid = await complete(client, owner, storage)
    pending = await reserve(client, owner, fid)
    vid = pending["version"]["id"]
    assert (await preview(client, owner, fid, version_id=vid)).status_code == 409
    assert storage.reads == 0

    async def unavailable(*args):
        raise StorageUnavailableError("provider-secret-must-stay-private")

    storage.inspect_upload = unavailable
    response = await preview(client, owner, fid)
    assert response.status_code == 503 and "provider-secret" not in response.text


@pytest.mark.asyncio
async def test_historical_preview_ignores_current_generation_but_rechecks_membership(
    client, db_factory, storage
):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    fid = await complete(client, owner, storage)
    async with db_factory() as db:
        vid = await db.scalar(select(FileVersion.id).where(FileVersion.file_id == UUID(fid)))

    async def transition():
        async with db_factory() as db:
            file = await db.get(File, UUID(fid))
            file.version_generation += 1
            await db.commit()

    storage.after_read = transition
    response = await preview(client, member, fid, version_id=str(vid))
    assert response.status_code == 200 and response.json()["version_id"] == str(vid)

    async def remove_member():
        result = await client.delete(
            f"/api/v1/organizations/current/members/{member['user']['id']}", headers=bearer(owner)
        )
        assert result.status_code == 204, result.text

    storage.after_read = remove_member
    assert (await preview(client, member, fid, version_id=str(vid))).status_code in (403, 404)
