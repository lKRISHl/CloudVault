import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Folder, User
from app.services.auth import AuthService
from app.services.folders import FolderService
from tests.api.test_auth import REGISTER_PAYLOAD, register_user
from tests.api.test_organizations import add_member, bearer

ROOT = "/api/v1/folders"


async def create(client, actor, name, parent=None):
    response = await client.post(
        ROOT, headers=bearer(actor), json={"name": name, "parent_id": parent}
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_folder_create_hierarchy_breadcrumbs_and_pagination(client):
    owner = await register_user(client)
    parent = await create(client, owner, "  Projects  ")
    child = await create(client, owner, "Nested", parent["id"])
    assert parent["name"] == "Projects" and parent["parent_id"] is None
    assert child["parent_id"] == parent["id"] and child["can_write"]
    root = (await client.get(ROOT, headers=bearer(owner))).json()
    assert [item["id"] for item in root["items"]] == [parent["id"]]
    page = (
        await client.get(ROOT, headers=bearer(owner), params={"parent_id": parent["id"]})
    ).json()
    assert [item["id"] for item in page["breadcrumbs"]] == [parent["id"]]
    assert page["parent"]["id"] == parent["id"] and page["items"][0]["id"] == child["id"]
    await create(client, owner, "Another")
    first = (await client.get(ROOT, headers=bearer(owner), params={"limit": 1})).json()
    second = (
        await client.get(ROOT, headers=bearer(owner), params={"limit": 1, "offset": 1})
    ).json()
    assert first["has_more"] and not second["has_more"]
    assert first["items"][0]["id"] != second["items"][0]["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", "   ", ".", "..", "a/b", "a\\b", "a\x00b", "a\nb", "x" * 256])
async def test_folder_names_reject_paths_control_characters_and_invalid_length(client, name):
    owner = await register_user(client)
    assert (await client.post(ROOT, headers=bearer(owner), json={"name": name})).status_code == 422


@pytest.mark.asyncio
async def test_duplicate_names_are_casefolded_normalized_and_scoped_to_parent(client):
    owner = await register_user(client)
    root = await create(client, owner, "Straße")
    assert (
        await client.post(ROOT, headers=bearer(owner), json={"name": " STRASSE "})
    ).status_code == 409
    await create(client, owner, "STRASSE", root["id"])
    accent = await create(client, owner, "Café")
    assert (
        await client.post(ROOT, headers=bearer(owner), json={"name": "Cafe\u0301"})
    ).status_code == 409
    changed = await client.patch(
        f"{ROOT}/{root['id']}", headers=bearer(owner), json={"name": "strasse"}
    )
    assert changed.status_code == 200 and changed.json()["id"] == root["id"]
    assert (
        await client.patch(
            f"{ROOT}/{root['id']}", headers=bearer(owner), json={"name": accent["name"]}
        )
    ).status_code == 409


@pytest.mark.asyncio
async def test_move_preserves_subtree_and_rejects_self_descendants_and_name_conflicts(client):
    owner = await register_user(client)
    source = await create(client, owner, "Source")
    child = await create(client, owner, "Child", source["id"])
    target = await create(client, owner, "Target")
    for destination in (source["id"], child["id"]):
        assert (
            await client.post(
                f"{ROOT}/{source['id']}/move",
                headers=bearer(owner),
                json={"parent_id": destination},
            )
        ).status_code == 409
    moved = await client.post(
        f"{ROOT}/{source['id']}/move", headers=bearer(owner), json={"parent_id": target["id"]}
    )
    assert moved.status_code == 200 and moved.json()["id"] == source["id"]
    path = (
        await client.get(ROOT, headers=bearer(owner), params={"parent_id": child["id"]})
    ).json()["breadcrumbs"]
    assert [item["name"] for item in path] == ["Target", "Source", "Child"]
    await create(client, owner, "Source")
    assert (
        await client.post(
            f"{ROOT}/{source['id']}/move", headers=bearer(owner), json={"parent_id": None}
        )
    ).status_code == 409
    assert (await client.get(f"{ROOT}/{child['id']}", headers=bearer(owner))).json()[
        "parent_id"
    ] == source["id"]


@pytest.mark.asyncio
async def test_permissions_creator_managers_and_read_only_members(client):
    owner = await register_user(client)
    first, _ = await add_member(client, owner, "first@example.com")
    second, _ = await add_member(client, owner, "second@example.com")
    admin, _ = await add_member(client, owner, "admin@example.com", "admin")
    folder = await create(client, first, "Member folder")
    read = await client.get(f"{ROOT}/{folder['id']}", headers=bearer(second))
    assert read.status_code == 200 and not read.json()["can_write"]
    assert (
        await client.patch(
            f"{ROOT}/{folder['id']}", headers=bearer(second), json={"name": "Denied"}
        )
    ).status_code == 403
    assert (
        await client.post(
            ROOT, headers=bearer(second), json={"name": "Denied", "parent_id": folder["id"]}
        )
    ).status_code == 403
    other = await create(client, second, "Second member")
    assert (
        await client.post(
            f"{ROOT}/{other['id']}/move", headers=bearer(second), json={"parent_id": folder["id"]}
        )
    ).status_code == 403
    assert (
        await client.patch(
            f"{ROOT}/{folder['id']}", headers=bearer(first), json={"name": "Creator rename"}
        )
    ).status_code == 200
    assert (
        await client.patch(
            f"{ROOT}/{folder['id']}", headers=bearer(admin), json={"name": "Admin rename"}
        )
    ).status_code == 200
    assert (
        await client.patch(
            f"{ROOT}/{folder['id']}", headers=bearer(owner), json={"name": "Owner rename"}
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_cross_tenant_folder_parent_and_payload_assignment_are_denied(client, db_factory):
    first = await register_user(client)
    other = await register_user(client, email="other@example.com", tenant_name="Other")
    first_folder = await create(client, first, "Documents")
    other_folder = await create(client, other, "Documents")
    for response in (
        await client.get(f"{ROOT}/{other_folder['id']}", headers=bearer(first)),
        await client.get(ROOT, headers=bearer(first), params={"parent_id": other_folder["id"]}),
        await client.post(
            ROOT, headers=bearer(first), json={"name": "Child", "parent_id": other_folder["id"]}
        ),
        await client.patch(
            f"{ROOT}/{other_folder['id']}", headers=bearer(first), json={"name": "Denied"}
        ),
        await client.post(
            f"{ROOT}/{first_folder['id']}/move",
            headers=bearer(first),
            json={"parent_id": other_folder["id"]},
        ),
    ):
        assert response.status_code == 404, response.text
    assert (
        await client.post(
            ROOT,
            headers=bearer(first),
            json={"name": "Injected", "tenant_id": other["user"]["tenant"]["id"]},
        )
    ).status_code == 422
    async with db_factory() as db:
        db.add(
            Folder(
                id=uuid4(),
                tenant_id=UUID(first["user"]["tenant"]["id"]),
                parent_id=UUID(other_folder["id"]),
                created_by=UUID(first["user"]["id"]),
                name="Invalid",
                name_key="invalid",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.asyncio
async def test_root_unique_name_constraint_and_self_parent_constraint(client, db_factory):
    owner = await register_user(client)
    folder = await create(client, owner, "Unique")
    async with db_factory() as db:
        db.add(
            Folder(
                tenant_id=UUID(owner["user"]["tenant"]["id"]),
                created_by=UUID(owner["user"]["id"]),
                name="Unique",
                name_key="unique",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
        stored = await db.get(Folder, UUID(folder["id"]))
        stored.parent_id = stored.id
        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.asyncio
async def test_folder_depth_checks_subtree_height_on_move(client, monkeypatch):
    import app.services.folders as service

    monkeypatch.setattr(service, "MAX_DEPTH", 3)
    owner = await register_user(client)
    top = await create(client, owner, "Top")
    middle = await create(client, owner, "Middle", top["id"])
    leaf = await create(client, owner, "Leaf", middle["id"])
    assert (
        await client.post(
            ROOT, headers=bearer(owner), json={"name": "Too deep", "parent_id": leaf["id"]}
        )
    ).status_code == 409
    subtree = await create(client, owner, "Subtree")
    await create(client, owner, "Child", subtree["id"])
    assert (
        await client.post(
            f"{ROOT}/{subtree['id']}/move", headers=bearer(owner), json={"parent_id": middle["id"]}
        )
    ).status_code == 409


@pytest.mark.asyncio
async def test_verified_workspace_and_authentication_gates(client):
    assert (await client.get(ROOT)).status_code == 401
    pending = (await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)).json()
    assert (
        await client.post(ROOT, headers=bearer(pending), json={"name": "Denied"})
    ).status_code == 403


@pytest.mark.asyncio
async def test_creator_deletion_retains_org_folder_for_manager(client, db_factory):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    folder = await create(client, member, "Team content")
    assert (
        await client.request(
            "DELETE",
            "/api/v1/account",
            headers=bearer(member),
            json={"password": "correct-horse", "confirmation": "DELETE"},
        )
    ).status_code == 204
    assert (await client.get(f"{ROOT}/{folder['id']}", headers=bearer(owner))).status_code == 200
    assert (
        await client.patch(
            f"{ROOT}/{folder['id']}", headers=bearer(owner), json={"name": "Retained"}
        )
    ).status_code == 200
    async with db_factory() as db:
        assert (await db.get(User, UUID(member["user"]["id"]))).deleted_at is not None


@pytest.mark.asyncio
async def test_concurrent_moves_cannot_create_cycle(client, db_factory):
    owner = await register_user(client)
    first, second = await create(client, owner, "First"), await create(client, owner, "Second")

    async def move(source, target):
        async with db_factory() as db:
            actor = await AuthService(db).get_user_in_tenant(
                UUID(owner["user"]["id"]), UUID(owner["user"]["tenant"]["id"])
            )
            try:
                await FolderService(db).move(actor, UUID(source["id"]), UUID(target["id"]))
                return 200
            except HTTPException as error:
                return error.status_code

    assert sorted(
        await asyncio.wait_for(asyncio.gather(move(first, second), move(second, first)), timeout=15)
    ) == [200, 409]
    async with db_factory() as db:
        folders = (await db.scalars(select(Folder))).all()
        assert sum(item.parent_id is None for item in folders) == 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_root_creation_has_one_winner(client, db_factory):
    owner = await register_user(client)

    async def attempt():
        async with db_factory() as db:
            actor = await AuthService(db).get_user_in_tenant(
                UUID(owner["user"]["id"]), UUID(owner["user"]["tenant"]["id"])
            )
            try:
                await FolderService(db).create(actor, "Same name", None)
                return 201
            except HTTPException as error:
                return error.status_code

    assert sorted(await asyncio.wait_for(asyncio.gather(attempt(), attempt()), timeout=15)) == [
        201,
        409,
    ]
