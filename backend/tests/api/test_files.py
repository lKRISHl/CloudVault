import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import File
from app.schemas.files import FileMetadataCreate
from app.services.auth import AuthService
from app.services.files import FileService
from tests.api.test_auth import REGISTER_PAYLOAD, register_user
from tests.api.test_folders import create as create_folder
from tests.api.test_organizations import add_member, bearer

ROOT = "/api/v1/files"


async def reserve(factory, session, name="Report.pdf", folder_id=None, **values):
    async with factory() as db:
        actor = await AuthService(db).get_user_in_tenant(
            UUID(session["user"]["id"]), UUID(session["user"]["tenant"]["id"])
        )
        return await FileService(db).reserve(
            actor,
            FileMetadataCreate(
                name=name,
                folder_id=folder_id,
                declared_size_bytes=123,
                declared_content_type="application/pdf",
                **values,
            ),
        )


@pytest.mark.asyncio
async def test_pending_metadata_root_folder_details_and_pages(client, db_factory):
    owner = await register_user(client)
    folder = await create_folder(client, owner, "Documents")
    root = await reserve(db_factory, owner)
    child = await reserve(db_factory, owner, folder_id=folder["id"])
    await reserve(db_factory, owner, name="Another.pdf")
    details = await client.get(f"{ROOT}/{child.id}", headers=bearer(owner))
    assert details.status_code == 200
    data = details.json()
    assert data["status"] == "pending" and data["declared_size_bytes"] == 123
    assert data["declared_content_type"] == "application/pdf" and data["can_write"]
    assert data["created_by"] == owner["user"]["id"] and data["folder_id"] == folder["id"]
    assert "download_url" not in data and "storage_key" not in data
    first = (await client.get(ROOT, headers=bearer(owner), params={"limit": 1})).json()
    second = (
        await client.get(ROOT, headers=bearer(owner), params={"limit": 1, "offset": 1})
    ).json()
    assert first["has_more"] and not second["has_more"]
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert second["items"][0]["id"] == str(root.id)
    nested = (
        await client.get(ROOT, headers=bearer(owner), params={"folder_id": folder["id"]})
    ).json()
    assert [item["id"] for item in nested["items"]] == [str(child.id)]
    assert (await client.get(ROOT, headers=bearer(owner), params={"limit": 101})).status_code == 422
    assert (
        await client.post(ROOT, headers=bearer(owner), json={"name": "Fake"})
    ).status_code == 405


@pytest.mark.asyncio
async def test_file_permissions_and_parent_authority(client, db_factory):
    owner = await register_user(client)
    first, _ = await add_member(client, owner, "first@example.com")
    second, _ = await add_member(client, owner, "second@example.com")
    folder = await create_folder(client, first, "Member documents")
    file = await reserve(db_factory, first, folder_id=folder["id"])
    for actor, writable in ((first, True), (owner, True), (second, False)):
        data = (await client.get(f"{ROOT}/{file.id}", headers=bearer(actor))).json()
        assert data["can_write"] is writable
    with pytest.raises(HTTPException) as denied:
        await reserve(db_factory, second, folder_id=folder["id"])
    assert denied.value.status_code == 403
    assert (await reserve(db_factory, second)).can_write


@pytest.mark.asyncio
async def test_files_cannot_cross_tenants_or_missing_folders(client, db_factory):
    first = await register_user(client)
    other = await register_user(client, email="other@example.com", tenant_name="Other")
    foreign = await create_folder(client, other, "Foreign")
    file = await reserve(db_factory, other, folder_id=foreign["id"])
    assert (await client.get(ROOT, headers=bearer(first))).json()["items"] == []
    assert (await client.get(f"{ROOT}/{file.id}", headers=bearer(first))).status_code == 404
    for folder in (foreign["id"], str(uuid4())):
        assert (
            await client.get(ROOT, headers=bearer(first), params={"folder_id": folder})
        ).status_code == 404
        with pytest.raises(HTTPException) as denied:
            await reserve(db_factory, first, folder_id=folder)
        assert denied.value.status_code == 404
    async with db_factory() as db:
        db.add(
            File(
                tenant_id=UUID(first["user"]["tenant"]["id"]),
                folder_id=UUID(foreign["id"]),
                created_by=UUID(first["user"]["id"]),
                name="Invalid",
                name_key="invalid",
                declared_size_bytes=0,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.parametrize(
    "values",
    [
        {"name": "../bad"},
        {"name": "a\\b"},
        {"name": "a\x00b"},
        {"name": " "},
        {"declared_size_bytes": -1},
        {"declared_size_bytes": 9007199254740992},
        {"declared_size_bytes": True},
        {"declared_content_type": "text/plain\r\nInjected: yes"},
        {"status": "ready"},
        {"tenant_id": str(uuid4())},
        {"created_by": str(uuid4())},
    ],
)
def test_invalid_or_forged_metadata_is_rejected(values):
    with pytest.raises(ValidationError):
        FileMetadataCreate(**{"name": "Report.pdf", "declared_size_bytes": 0, **values})


@pytest.mark.asyncio
async def test_file_name_normalization_and_concurrent_reservation(client, db_factory):
    owner = await register_user(client)
    file = await reserve(db_factory, owner, name="  Cafe\u0301.PDF  ")
    assert file.name == "Café.PDF"
    with pytest.raises(HTTPException) as conflict:
        await reserve(db_factory, owner, name="CAFÉ.pdf")
    assert conflict.value.status_code == 409

    async def attempt():
        try:
            await reserve(db_factory, owner, name="Concurrent.pdf")
            return 201
        except HTTPException as error:
            return error.status_code

    assert sorted(await asyncio.wait_for(asyncio.gather(attempt(), attempt()), 15)) == [201, 409]


@pytest.mark.asyncio
async def test_creator_deletion_and_folder_move_preserve_file_identity(client, db_factory):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    folder = await create_folder(client, member, "Member documents")
    target = await create_folder(client, owner, "Archive")
    file = await reserve(db_factory, member, folder_id=folder["id"])
    assert (
        await client.post(
            f"/api/v1/folders/{folder['id']}/move",
            headers=bearer(owner),
            json={"parent_id": target["id"]},
        )
    ).status_code == 200
    assert (
        await client.request(
            "DELETE",
            "/api/v1/account",
            headers=bearer(member),
            json={"password": "correct-horse", "confirmation": "DELETE"},
        )
    ).status_code == 204
    data = (await client.get(f"{ROOT}/{file.id}", headers=bearer(owner))).json()
    assert (
        data["folder_id"] == folder["id"]
        and data["created_by"] == member["user"]["id"]
        and data["can_write"]
    )
    assert (await client.get(f"{ROOT}/{file.id}", headers=bearer(member))).status_code == 401


@pytest.mark.asyncio
async def test_file_database_constraints_and_authentication(client, db_factory):
    assert (await client.get(ROOT)).status_code == 401
    pending = (await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)).json()
    assert (await client.get(ROOT, headers=bearer(pending))).status_code == 403
    owner = await register_user(client, email="verified@example.com", tenant_name="Verified")
    file = await reserve(db_factory, owner)
    async with db_factory() as db:
        stored = await db.get(File, file.id)
        stored.status = "ready"
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
        stored = await db.get(File, file.id)
        stored.declared_size_bytes = -1
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
        stored = await db.get(File, file.id)
        db.add(
            File(
                tenant_id=stored.tenant_id,
                created_by=stored.created_by,
                name=stored.name,
                name_key=stored.name_key,
                declared_size_bytes=0,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
        assert len(list(await db.scalars(select(File)))) == 1
