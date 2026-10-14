from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update

from app.models import File, Membership
from app.models.account import RateLimit
from tests.api.test_auth import REGISTER_PAYLOAD, register_user
from tests.api.test_files import reserve
from tests.api.test_folders import create as create_folder
from tests.api.test_organizations import add_member, bearer

URL = "/api/v1/files/search"


async def search(client, actor, **params):
    response = await client.get(URL, headers=bearer(actor), params=params)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


@pytest.mark.asyncio
async def test_normalized_literal_filename_search_and_empty_results(client, db_factory):
    owner = await register_user(client)
    for name in [
        "Résumé.pdf",
        "STRASSE.txt",
        "Budget 50%.pdf",
        "Budget 500.pdf",
        "item_1.txt",
        "itemX1.txt",
    ]:
        await reserve(db_factory, owner, name)
    assert [
        row["name"] for row in (await search(client, owner, q="  RE\u0301SUME\u0301  "))["items"]
    ] == ["Résumé.pdf"]
    assert (await search(client, owner, q="straße"))["items"][0]["name"] == "STRASSE.txt"
    assert (await search(client, owner, q="50%"))["items"][0]["name"] == "Budget 50%.pdf"
    assert len((await search(client, owner, q="item_"))["items"]) == 1
    assert not (await search(client, owner, q="' OR 1=1 --"))["items"]
    assert not (await search(client, owner, q="\\"))["items"]
    assert len((await search(client, owner))["items"]) == 6


@pytest.mark.asyncio
async def test_scope_creator_and_metadata_filters(client, db_factory):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    folder = await create_folder(client, owner, "Reports")
    root = await reserve(db_factory, member, "Root.pdf")
    nested = await reserve(db_factory, owner, "Nested.pdf", folder_id=folder["id"])
    async with db_factory() as db:
        file = await db.get(File, nested.id)
        file.declared_size_bytes = 500
        file.declared_content_type = "text/plain"
        await db.commit()
    assert len((await search(client, member))["items"]) == 2
    assert not (await search(client, member))["items"][0]["can_write"]
    assert (await search(client, owner, scope="root"))["items"][0]["id"] == str(root.id)
    assert (await search(client, owner, scope="folder", folder_id=folder["id"]))["items"][0][
        "id"
    ] == str(nested.id)
    assert (await search(client, owner, scope="folder", folder_id=folder["id"]))["items"][0][
        "folder_name"
    ] == "Reports"
    assert (await search(client, owner, created_by=member["user"]["id"]))["items"][0]["id"] == str(
        root.id
    )
    assert (
        await search(
            client, owner, min_bytes=400, max_bytes=500, declared_content_type="text/plain"
        )
    )["items"][0]["id"] == str(nested.id)
    assert not (await search(client, owner, status="uploaded"))["items"]
    assert not (await search(client, owner, upload_method="multipart"))["items"]


@pytest.mark.asyncio
async def test_uploaded_filter_and_cleanup_tombstones_hide_private_references(client, db_factory):
    owner = await register_user(client)
    uploaded = await reserve(db_factory, owner, "Uploaded.pdf")
    cleaned = await reserve(db_factory, owner, "Expired.pdf")
    async with db_factory() as db:
        for id in [uploaded.id, cleaned.id]:
            file = await db.get(File, id)
            file.object_id, file.storage_bucket, file.upload_request_id = (
                uuid4(),
                "cv-test-search",
                uuid4(),
            )
            file.upload_expires_at, file.expected_checksum_sha256 = datetime.now(UTC), "a" * 44
            if id == uploaded.id:
                file.status, file.size_bytes, file.checksum_sha256 = "uploaded", 123, "a" * 44
                file.content_type, file.storage_etag, file.completed_at = (
                    "application/octet-stream",
                    "etag",
                    datetime.now(UTC),
                )
            else:
                file.upload_cleanup_at = datetime.now(UTC)
        await db.commit()
    rows = (await search(client, owner, status="uploaded"))["items"]
    assert len(rows) == 1 and rows[0]["id"] == str(uploaded.id)
    assert not {
        "storage_bucket",
        "object_id",
        "expected_checksum_sha256",
        "upload_request_id",
    }.intersection(rows[0])
    assert not (await search(client, owner, q="Expired"))["items"]


@pytest.mark.asyncio
async def test_sorting_and_pages_are_deterministic_for_ties(client, db_factory):
    owner = await register_user(client)
    for index, name in enumerate(["Zulu.pdf", "alpha.pdf", "Beta.pdf"]):
        file = await reserve(db_factory, owner, name)
        async with db_factory() as db:
            row = await db.get(File, file.id)
            row.declared_size_bytes = index
            row.created_at = row.updated_at = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(
                days=index
            )
            await db.commit()
    assert [row["name"] for row in (await search(client, owner))["items"]] == [
        "alpha.pdf",
        "Beta.pdf",
        "Zulu.pdf",
    ]
    for key in ("size", "created_at", "updated_at"):
        assert (await search(client, owner, sort=key, direction="desc"))["items"][0][
            "name"
        ] == "Beta.pdf"
    first = await search(client, owner, sort="size", limit=2)
    second = await search(client, owner, sort="size", limit=2, offset=2)
    assert first["has_more"] and not second["has_more"]
    assert len({row["id"] for row in first["items"] + second["items"]}) == 3
    tie_a = await search(client, owner, sort="name", limit=1)
    assert tie_a == await search(client, owner, sort="name", limit=1)
    folder = await create_folder(client, owner, "Ties")
    await reserve(db_factory, owner, "alpha.pdf", folder_id=folder["id"])
    tied = await search(client, owner, q="alpha", limit=1)
    next_tied = await search(client, owner, q="alpha", limit=1, offset=1)
    assert tied["has_more"] and tied["items"][0]["id"] < next_tied["items"][0]["id"]


@pytest.mark.asyncio
async def test_search_has_separate_bounded_rate_budget(client, db_factory):
    owner = await register_user(client)
    for _ in range(12):
        await search(client, owner)
    async with db_factory() as db:
        await db.execute(update(RateLimit).values(hits=4800))
        await db.commit()
    assert (await client.get(URL, headers=bearer(owner))).status_code == 429


@pytest.mark.asyncio
async def test_search_cannot_cross_tenants_folders_or_revoked_membership(client, db_factory):
    owner = await register_user(client)
    other = await register_user(client, email="foreign-search@example.com", tenant_name="Other")
    folder = await create_folder(client, other, "Foreign")
    await reserve(db_factory, other, "Secret.pdf", folder_id=folder["id"])
    assert not (await search(client, owner, q="Secret"))["items"]
    assert not (await search(client, owner, created_by=other["user"]["id"]))["items"]
    for id in [folder["id"], str(uuid4())]:
        assert (
            await client.get(
                URL, headers=bearer(owner), params={"scope": "folder", "folder_id": id}
            )
        ).status_code == 404
    assert (await client.get(URL)).status_code == 401
    member, _ = await add_member(client, owner)
    async with db_factory() as db:
        membership = await db.get(
            Membership, (UUID(owner["user"]["tenant"]["id"]), UUID(member["user"]["id"]))
        )
        membership.revoked_at = datetime.now(UTC)
        await db.commit()
    assert (await client.get(URL, headers=bearer(member))).status_code in (401, 403)


@pytest.mark.asyncio
async def test_unverified_accounts_and_invalid_queries_fail_closed(client):
    unverified = (await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)).json()
    assert (await client.get(URL, headers=bearer(unverified))).status_code == 403
    owner = await register_user(client, email="verified-search@example.com")
    for params in [
        {"q": "a" * 129},
        {"q": "a\n"},
        {"limit": 101},
        {"offset": 10001},
        {"min_bytes": -1},
        {"min_bytes": 10, "max_bytes": 2},
        {"scope": "folder"},
        {"folder_id": str(uuid4())},
        {"sort": "name; DROP TABLE files"},
        {"status": "cleaned"},
        {"tenant_id": str(uuid4())},
    ]:
        assert (await client.get(URL, headers=bearer(owner), params=params)).status_code == 422, (
            params
        )
