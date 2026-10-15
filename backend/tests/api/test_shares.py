import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.models import Membership, ShareLink
from app.storage.base import StorageUnavailableError
from tests.api.test_auth import register_user
from tests.api.test_downloads import uploaded
from tests.api.test_organizations import add_member, bearer
from tests.api.test_uploads import ROOT, start, storage

__all__ = ["storage"]


@pytest_asyncio.fixture(autouse=True)
async def public_storage(storage):
    from contextlib import asynccontextmanager

    from app.api.storage import get_share_storage_factory
    from app.main import app

    @asynccontextmanager
    async def factory(tenant_id):
        storage.share_tenant = tenant_id
        yield storage

    app.dependency_overrides[get_share_storage_factory] = lambda: factory
    yield
    app.dependency_overrides.pop(get_share_storage_factory, None)


async def create(client, owner, file_id, **options):
    response = await client.post(f"{ROOT}/{file_id}/shares", headers=bearer(owner), json=options)
    assert response.status_code == 201, response.text
    result = response.json()
    return result, result["share_url"].split("#token=")[1]


@pytest.mark.asyncio
async def test_share_password_metadata_download_and_secret_storage(client, db_factory, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    created, token = await create(client, owner, fid, password="separate-secret", max_downloads=1)
    assert (
        created["password_required"]
        and "token_hash" not in created
        and "password_hash" not in created
    )
    async with db_factory() as db:
        row = await db.get(ShareLink, UUID(created["id"]))
        assert row.token_hash != token and row.password_hash != "separate-secret"
    for password in ["", "wrong-secret"]:
        response = await client.post(
            "/api/v1/shares/access", json={"token": token, "password": password}
        )
        assert response.status_code == 404 and "Report" not in response.text
        assert response.headers["cache-control"] == "no-store"
    payload = {"token": token, "password": "separate-secret"}
    response = await client.post("/api/v1/shares/access", json=payload)
    assert response.status_code == 200 and response.json()["name"] == "Report.txt"
    assert set(response.json()) == {
        "name",
        "size_bytes",
        "expires_at",
        "allow_download",
        "grants_remaining",
    }

    async def sign(ref, name, ttl):
        assert ref.tenant_id == storage.share_tenant
        assert (
            str(ref.tenant_id) == owner["user"]["tenant"]["id"]
            and name == "Report.txt"
            and ttl <= 300
        )
        return "https://storage.invalid/shared"

    storage.presign_download = sign
    response = await client.post("/api/v1/shares/download-url", json=payload)
    assert response.status_code == 200 and response.json()["download_url"].endswith("shared")
    assert (await client.post("/api/v1/shares/download-url", json=payload)).status_code == 403
    assert not (await client.post("/api/v1/shares/access", json=payload)).json()["allow_download"]
    listing = await client.get(f"{ROOT}/{fid}/shares", headers=bearer(owner))
    assert listing.json()["items"][0]["download_grants"] == 1 and token not in listing.text


@pytest.mark.asyncio
async def test_share_creation_management_tenant_and_readonly_permissions(client, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    member, _ = await add_member(client, owner)
    outsider = await register_user(client, email="foreign-share@example.com")
    for actor, status in [(member, 403), (outsider, 404)]:
        assert (
            await client.post(f"{ROOT}/{fid}/shares", headers=bearer(actor), json={})
        ).status_code == status
        assert (
            await client.get(f"{ROOT}/{fid}/shares", headers=bearer(actor))
        ).status_code == status
    assert (await client.post(f"{ROOT}/{fid}/shares", json={})).status_code == 401
    pending = await start(client, owner, name="pending.txt")
    assert (
        await client.post(f"{ROOT}/{pending['file']['id']}/shares", headers=bearer(owner), json={})
    ).status_code == 409
    link, token = await create(client, owner, fid, allow_download=False)
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 200
    assert (
        await client.post("/api/v1/shares/download-url", json={"token": token})
    ).status_code == 403
    assert (
        await client.delete(f"{ROOT}/{fid}/shares/{link['id']}", headers=bearer(outsider))
    ).status_code == 404
    assert (
        await client.delete(f"{ROOT}/{fid}/shares/{uuid4()}", headers=bearer(owner))
    ).status_code == 404
    for _ in range(2):
        assert (
            await client.delete(f"{ROOT}/{fid}/shares/{link['id']}", headers=bearer(owner))
        ).status_code == 204
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 404


@pytest.mark.asyncio
async def test_expired_unknown_and_invalid_links_and_payloads(client, db_factory, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    for payload in [
        {"expires_in_hours": 0},
        {"expires_in_hours": 721},
        {"password": "short"},
        {"max_downloads": 0},
        {"tenant_id": str(uuid4())},
    ]:
        assert (
            await client.post(f"{ROOT}/{fid}/shares", headers=bearer(owner), json=payload)
        ).status_code == 422
    link, token = await create(client, owner, fid)
    async with db_factory() as db:
        row = await db.get(ShareLink, UUID(link["id"]))
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    for raw in [token, "a" * 43]:
        assert (await client.post("/api/v1/shares/access", json={"token": raw})).status_code == 404
    assert (
        await client.post("/api/v1/shares/access", json={"token": "invalid"})
    ).status_code == 422


@pytest.mark.asyncio
async def test_publisher_removal_permanently_revokes_links(client, db_factory, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    fid = await uploaded(client, member)
    link, token = await create(client, member, fid)
    assert (
        await client.delete(
            f"/api/v1/organizations/current/members/{member['user']['id']}", headers=bearer(owner)
        )
    ).status_code == 204
    async with db_factory() as db:
        row = await db.get(ShareLink, UUID(link["id"]))
        assert row.revoked_at is not None
        membership = await db.get(
            Membership, (UUID(owner["user"]["tenant"]["id"]), UUID(member["user"]["id"]))
        )
        membership.revoked_at = None
        await db.commit()
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 404


@pytest.mark.asyncio
async def test_failed_provider_does_not_consume_grant_and_expiry_caps_ttl(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    link, token = await create(client, owner, fid, max_downloads=1)
    storage.error = StorageUnavailableError("private details")
    response = await client.post("/api/v1/shares/download-url", json={"token": token})
    assert response.status_code == 503 and "private details" not in response.text
    async with db_factory() as db:
        row = await db.get(ShareLink, UUID(link["id"]))
        assert row.download_grants == 0
        row.expires_at = datetime.now(UTC) + timedelta(seconds=25)
        await db.commit()
    storage.error = None

    async def sign(ref, name, ttl):
        assert 1 <= ttl <= 25
        return "https://storage.invalid/bounded"

    storage.presign_download = sign
    assert (
        await client.post("/api/v1/shares/download-url", json={"token": token})
    ).status_code == 200


@pytest.mark.asyncio
async def test_public_ip_budget_applies_to_unknown_tokens(client):
    # Invalid capabilities consume the same persistent IP budget.
    for index in range(100):
        response = await client.post("/api/v1/shares/access", json={"token": f"{index:043d}"})
        assert response.status_code == 404
    assert (await client.post("/api/v1/shares/access", json={"token": "x" * 43})).status_code == 429


@pytest.mark.asyncio
async def test_concurrent_single_grant_cannot_be_overspent(client, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    _, token = await create(client, owner, fid, max_downloads=1)

    async def sign(*args):
        await asyncio.sleep(0.05)
        return "https://storage.invalid/one"

    storage.presign_download = sign
    responses = await asyncio.gather(
        *[client.post("/api/v1/shares/download-url", json={"token": token}) for _ in range(2)]
    )
    assert sorted(response.status_code for response in responses) == [200, 403]


@pytest.mark.asyncio
async def test_role_changes_account_deletion_and_unverified_publishers(client, db_factory, storage):
    from app.models import User

    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    fid = await uploaded(client, member)
    link, token = await create(client, member, fid)
    changed = await client.patch(
        f"/api/v1/organizations/current/members/{member['user']['id']}",
        headers=bearer(owner),
        json={"role": "admin"},
    )
    assert changed.status_code == 200
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 404
    link, token = await create(client, member, fid)
    async with db_factory() as db:
        user = await db.get(User, UUID(member["user"]["id"]))
        user.email_verified = False
        await db.commit()
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 404
    async with db_factory() as db:
        user = await db.get(User, UUID(member["user"]["id"]))
        user.email_verified = True
        await db.commit()
    deleted = await client.request(
        "DELETE",
        "/api/v1/account",
        headers=bearer(member),
        json={"password": "correct-horse", "confirmation": "DELETE"},
    )
    assert deleted.status_code == 204, deleted.text
    async with db_factory() as db:
        assert (await db.get(ShareLink, UUID(link["id"]))).revoked_at is not None
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 404


@pytest.mark.asyncio
async def test_share_list_pagination_and_file_binding(client, db_factory, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    _, token = await create(client, owner, fid)
    async with db_factory() as db:
        rows = [
            ShareLink(
                tenant_id=UUID(owner["user"]["tenant"]["id"]),
                file_id=UUID(fid),
                created_by=UUID(owner["user"]["id"]),
                token_hash=f"{index:064d}",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                allow_download=True,
            )
            for index in range(26)
        ]
        db.add_all(rows)
        await db.commit()
    first = (await client.get(f"{ROOT}/{fid}/shares", headers=bearer(owner))).json()
    second = (await client.get(f"{ROOT}/{fid}/shares?offset=25", headers=bearer(owner))).json()
    assert len(first["items"]) == 25 and first["has_more"]
    assert len(second["items"]) == 2 and not second["has_more"]
    assert not ({row["id"] for row in first["items"]} & {row["id"] for row in second["items"]})
    assert token not in str(first) + str(second)
    other_fid = await uploaded_with_name(client, owner)
    assert (
        await client.delete(
            f"{ROOT}/{other_fid}/shares/{first['items'][0]['id']}", headers=bearer(owner)
        )
    ).status_code == 404


async def uploaded_with_name(client, owner):
    ticket = await start(client, owner, name="Other.txt")
    fid = ticket["file"]["id"]
    assert (await client.post(f"{ROOT}/{fid}/complete", headers=bearer(owner))).status_code == 200
    return fid


@pytest.mark.asyncio
async def test_expiry_during_provider_inspection_does_not_issue_or_count(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    link, token = await create(client, owner, fid)
    async with db_factory() as db:
        row = await db.get(ShareLink, UUID(link["id"]))
        row.expires_at = datetime.now(UTC) + timedelta(seconds=2)
        await db.commit()

    async def inspect(ref):
        await asyncio.sleep(2.1)
        return storage.info

    storage.inspect_upload = inspect
    called = False

    async def sign(*args):
        nonlocal called
        called = True
        return "https://storage.invalid/expired"

    storage.presign_download = sign
    assert (
        await client.post("/api/v1/shares/download-url", json={"token": token})
    ).status_code == 404
    assert not called
    async with db_factory() as db:
        assert (await db.get(ShareLink, UUID(link["id"]))).download_grants == 0
