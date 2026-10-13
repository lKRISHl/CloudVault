import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token, hash_refresh_token
from app.models import Invitation, Membership, UserRole
from app.schemas.organizations import AcceptInvitation
from app.services.auth import AuthService
from app.services.organizations import OrganizationService
from tests.api.test_auth import register_user, verify_test_account

PREFIX = "/api/v1/organizations/current"


def bearer(session):
    return {"Authorization": f"Bearer {session['access_token']}"}


async def add_member(client, owner, email="member@example.com", role="member"):
    invitation = await client.post(
        f"{PREFIX}/invitations",
        headers=bearer(owner),
        json={
            "email": email,
            "role": role,
        },
    )
    assert invitation.status_code == 201, invitation.text
    accepted = await client.post(
        "/api/v1/organizations/invitations/accept",
        json={
            "token": invitation.json()["token"],
            "full_name": "Team Member",
            "password": "correct-horse",
        },
    )
    assert accepted.status_code == 201, accepted.text
    data = accepted.json()
    await verify_test_account(client, email)
    data["user"]["email_verified"] = True
    return data, invitation.json()


@pytest.mark.asyncio
async def test_registration_creates_owner_membership(client, db_factory):
    owner = await register_user(client)
    async with db_factory() as db:
        membership = (await db.execute(select(Membership))).scalar_one()
        assert str(membership.user_id) == owner["user"]["id"]
        assert str(membership.tenant_id) == owner["user"]["tenant"]["id"]
        assert membership.role == UserRole.OWNER


@pytest.mark.asyncio
async def test_profile_read_update_and_field_validation(client):
    owner = await register_user(client)
    profile = await client.get("/api/v1/users/me", headers=bearer(owner))
    assert profile.status_code == 200
    changed = await client.patch(
        "/api/v1/users/me",
        headers=bearer(owner),
        json={
            "full_name": "  Updated Name  ",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["full_name"] == "Updated Name"
    for payload in ({"full_name": "   "}, {"full_name": "Name", "role": "admin"}):
        assert (
            await client.patch(
                "/api/v1/users/me",
                headers=bearer(owner),
                json=payload,
            )
        ).status_code == 422


@pytest.mark.asyncio
async def test_organization_read_rename_and_member_restriction(client):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    org = await client.get(PREFIX, headers=bearer(member))
    assert org.status_code == 200
    assert org.json()["id"] == owner["user"]["tenant"]["id"]
    denied = await client.patch(PREFIX, headers=bearer(member), json={"name": "Intruder"})
    assert denied.status_code == 403
    renamed = await client.patch(PREFIX, headers=bearer(owner), json={"name": "  New Org  "})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "New Org"
    assert renamed.json()["slug"] == owner["user"]["tenant"]["slug"]
    assert (
        await client.patch(PREFIX, headers=bearer(owner), json={"name": " "})
    ).status_code == 422


@pytest.mark.asyncio
async def test_invitation_onboards_in_same_tenant_and_cannot_replay(client, db_factory):
    owner = await register_user(client)
    member, invitation = await add_member(client, owner)
    assert member["user"]["tenant"]["id"] == owner["user"]["tenant"]["id"]
    assert member["user"]["role"] == "member"
    assert member["user"]["email"] == "member@example.com"
    replay = await client.post(
        "/api/v1/organizations/invitations/accept",
        json={
            "token": invitation["token"],
            "full_name": "Replay",
            "password": "correct-horse",
        },
    )
    assert replay.status_code == 400
    async with db_factory() as db:
        stored = (await db.execute(select(Invitation))).scalar_one()
        assert stored.token_hash == hash_refresh_token(invitation["token"])
        assert stored.token_hash != invitation["token"]
        assert stored.consumed_at is not None
    listing = await client.get(f"{PREFIX}/members", headers=bearer(owner))
    assert len(listing.json()) == 2
    assert "password_hash" not in listing.text
    assert (await client.get(f"{PREFIX}/members?limit=1", headers=bearer(member))).json()
    assert (
        await client.get(f"{PREFIX}/members?limit=101", headers=bearer(owner))
    ).status_code == 422


@pytest.mark.asyncio
async def test_owner_changes_role_and_stale_jwt_cannot_keep_admin_permissions(client):
    owner = await register_user(client)
    admin, _ = await add_member(client, owner, "admin@example.com", "admin")
    url = f"{PREFIX}/members/{admin['user']['id']}"
    assert (
        await client.patch(url, headers=bearer(owner), json={"role": "member"})
    ).status_code == 200
    assert (
        await client.patch(PREFIX, headers=bearer(admin), json={"name": "Denied"})
    ).status_code == 403
    me = await client.get("/api/v1/auth/me", headers=bearer(admin))
    assert me.json()["role"] == "member"
    assert (
        await client.patch(url, headers=bearer(owner), json={"role": "owner"})
    ).status_code == 422
    owner_url = f"{PREFIX}/members/{owner['user']['id']}"
    assert (
        await client.patch(owner_url, headers=bearer(owner), json={"role": "member"})
    ).status_code == 409
    assert (await client.delete(owner_url, headers=bearer(owner))).status_code == 409


@pytest.mark.asyncio
async def test_admin_can_invite_and_remove_members_but_cannot_manage_admins(client):
    owner = await register_user(client)
    admin, _ = await add_member(client, owner, "admin@example.com", "admin")
    member, _ = await add_member(client, admin)
    second_admin, _ = await add_member(client, owner, "otheradmin@example.com", "admin")
    assert (
        await client.patch(PREFIX, headers=bearer(admin), json={"name": "Admin Rename"})
    ).status_code == 200
    denied = await client.post(
        f"{PREFIX}/invitations",
        headers=bearer(admin),
        json={
            "email": "newadmin@example.com",
            "role": "admin",
        },
    )
    assert denied.status_code == 403
    target = f"{PREFIX}/members/{second_admin['user']['id']}"
    assert (await client.delete(target, headers=bearer(admin))).status_code == 403
    assert (
        await client.patch(target, headers=bearer(admin), json={"role": "member"})
    ).status_code == 403
    assert (
        await client.delete(
            f"{PREFIX}/members/{member['user']['id']}",
            headers=bearer(admin),
        )
    ).status_code == 204
    assert (await client.get("/api/v1/users/me", headers=bearer(member))).status_code == 401
    # The cookie belongs to the most recently onboarded admin, not the removed member.
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "member@example.com",
            "password": "correct-horse",
        },
    )
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_cross_tenant_resources_are_hidden_and_lists_are_scoped(client):
    first = await register_user(client)
    member, _ = await add_member(client, first)
    other = await register_user(client, email="other@example.com", tenant_name="Other")
    members = (await client.get(f"{PREFIX}/members", headers=bearer(other))).json()
    assert [row["user_id"] for row in members] == [other["user"]["id"]]
    target = f"{PREFIX}/members/{member['user']['id']}"
    assert (
        await client.patch(target, headers=bearer(other), json={"role": "admin"})
    ).status_code == 404
    assert (await client.delete(target, headers=bearer(other))).status_code == 404
    invitation = await client.post(
        f"{PREFIX}/invitations",
        headers=bearer(first),
        json={
            "email": "new@example.com",
            "role": "member",
        },
    )
    assert (
        await client.delete(
            f"{PREFIX}/invitations/{invitation.json()['id']}",
            headers=bearer(other),
        )
    ).status_code == 404
    assert (await client.get(f"{PREFIX}/invitations", headers=bearer(other))).json() == []


@pytest.mark.asyncio
async def test_members_cannot_invite_or_view_invitations(client):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    assert (await client.get(f"{PREFIX}/invitations", headers=bearer(member))).status_code == 403
    assert (
        await client.post(
            f"{PREFIX}/invitations",
            headers=bearer(member),
            json={
                "email": "new@example.com",
                "role": "member",
            },
        )
    ).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidity", ["expired", "revoked", "unknown"])
async def test_invalid_invitations_do_not_create_users(client, db_factory, invalidity):
    owner = await register_user(client)
    invited = await client.post(
        f"{PREFIX}/invitations",
        headers=bearer(owner),
        json={
            "email": "invite@example.com",
            "role": "member",
        },
    )
    token = invited.json()["token"]
    if invalidity == "revoked":
        assert (
            await client.delete(
                f"{PREFIX}/invitations/{invited.json()['id']}",
                headers=bearer(owner),
            )
        ).status_code == 204
    elif invalidity == "expired":
        async with db_factory() as db:
            await db.execute(
                update(Invitation).values(
                    expires_at=datetime.now(UTC) - timedelta(days=1),
                )
            )
            await db.commit()
    else:
        token = "x" * 64
    result = await client.post(
        "/api/v1/organizations/invitations/accept",
        json={
            "token": token,
            "full_name": "Name",
            "password": "correct-horse",
        },
    )
    assert result.status_code == 400
    assert len((await client.get(f"{PREFIX}/members", headers=bearer(owner))).json()) == 1


@pytest.mark.asyncio
async def test_missing_membership_denies_even_a_valid_owner_jwt(client, db_factory):
    owner = await register_user(client)
    async with db_factory() as db:
        await db.execute(delete(Membership))
        await db.commit()
    assert (await client.get(PREFIX, headers=bearer(owner))).status_code == 401
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


@pytest.mark.asyncio
async def test_jwt_role_cannot_escalate_a_member(client):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    token = create_access_token(
        user_id=UUID(member["user"]["id"]),
        tenant_id=UUID(member["user"]["tenant"]["id"]),
        role="owner",
        session_id=UUID(
            __import__("jwt").decode(member["access_token"], options={"verify_signature": False})[
                "sid"
            ]
        ),
    )
    denied = await client.patch(
        PREFIX,
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Denied",
        },
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_membership_database_constraint_rejects_cross_tenant_link(client, db_factory):
    first = await register_user(client)
    other = await register_user(client, email="other@example.com", tenant_name="Other")
    async with db_factory() as db:
        await db.execute(delete(Membership).where(Membership.user_id == UUID(first["user"]["id"])))
        db.add(
            Membership(
                user_id=UUID(first["user"]["id"]),
                tenant_id=UUID(other["user"]["tenant"]["id"]),
                role=UserRole.MEMBER,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/v1/users/me", None),
        ("PATCH", "/api/v1/users/me", {"full_name": "Name"}),
        ("GET", PREFIX, None),
        ("PATCH", PREFIX, {"name": "Name"}),
        ("GET", f"{PREFIX}/members", None),
        ("GET", f"{PREFIX}/invitations", None),
        ("POST", f"{PREFIX}/invitations", {"email": "new@example.com", "role": "member"}),
    ],
)
async def test_phase_two_resources_require_authentication(client, method, path, payload):
    result = await client.request(method, path, json=payload)
    assert result.status_code == 401


@pytest.mark.asyncio
async def test_removal_revokes_refresh_cookie_and_access_token(client):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    assert (
        await client.delete(
            f"{PREFIX}/members/{member['user']['id']}",
            headers=bearer(owner),
        )
    ).status_code == 204
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=bearer(member))).status_code == 401


@pytest.mark.asyncio
async def test_demotion_revokes_invitations_created_by_the_former_admin(client):
    owner = await register_user(client)
    admin, _ = await add_member(client, owner, "admin@example.com", "admin")
    invite = await client.post(
        f"{PREFIX}/invitations",
        headers=bearer(admin),
        json={
            "email": "new@example.com",
            "role": "member",
        },
    )
    assert invite.status_code == 201
    changed = await client.patch(
        f"{PREFIX}/members/{admin['user']['id']}",
        headers=bearer(owner),
        json={"role": "member"},
    )
    assert changed.status_code == 200
    accepted = await client.post(
        "/api/v1/organizations/invitations/accept",
        json={
            "token": invite.json()["token"],
            "full_name": "Name",
            "password": "correct-horse",
        },
    )
    assert accepted.status_code == 400


@pytest.mark.asyncio
async def test_reinviting_supersedes_previous_token_and_rejects_existing_accounts(client):
    owner = await register_user(client)
    payload = {"email": "new@example.com", "role": "member"}
    previous = await client.post(f"{PREFIX}/invitations", headers=bearer(owner), json=payload)
    replacement = await client.post(f"{PREFIX}/invitations", headers=bearer(owner), json=payload)
    assert replacement.status_code == 201
    accept_payload = {
        "token": previous.json()["token"],
        "full_name": "Name",
        "password": "correct-horse",
    }
    assert (
        await client.post(
            "/api/v1/organizations/invitations/accept",
            json=accept_payload,
        )
    ).status_code == 400
    accept_payload["token"] = replacement.json()["token"]
    assert (
        await client.post(
            "/api/v1/organizations/invitations/accept",
            json=accept_payload,
        )
    ).status_code == 201
    assert (
        await client.post(
            f"{PREFIX}/invitations",
            headers=bearer(owner),
            json=payload,
        )
    ).status_code == 409


@pytest.mark.asyncio
async def test_failed_session_creation_rolls_back_invitation_and_membership(
    client, db_factory, monkeypatch
):
    owner = await register_user(client)
    invitation = await client.post(
        f"{PREFIX}/invitations",
        headers=bearer(owner),
        json={
            "email": "new@example.com",
            "role": "member",
        },
    )
    payload = {
        "token": invitation.json()["token"],
        "full_name": "Name",
        "password": "correct-horse",
    }

    async def fail(*_):
        raise RuntimeError("Simulated session failure")

    with monkeypatch.context() as patch:
        patch.setattr(AuthService, "issue_session", fail)
        with pytest.raises(RuntimeError, match="Simulated session failure"):
            await client.post("/api/v1/organizations/invitations/accept", json=payload)
    async with db_factory() as db:
        invitation = (await db.execute(select(Invitation))).scalar_one()
        assert invitation.consumed_at is None
        assert len((await db.scalars(select(Membership))).all()) == 1
    assert (
        await client.post("/api/v1/organizations/invitations/accept", json=payload)
    ).status_code == 201


@pytest.mark.asyncio
async def test_concurrent_invitation_acceptance_creates_one_membership(
    client, db_factory, monkeypatch
):
    owner = await register_user(client)
    invitation = await client.post(
        f"{PREFIX}/invitations",
        headers=bearer(owner),
        json={
            "email": "new@example.com",
            "role": "member",
        },
    )
    payload = AcceptInvitation(
        token=invitation.json()["token"],
        full_name="Name",
        password="correct-horse",
    )
    ready = asyncio.Event()
    arrivals = 0

    async def attempt():
        nonlocal arrivals
        async with db_factory() as db:
            original_scalar = db.scalar

            async def read_invitation(*args, **kwargs):
                nonlocal arrivals
                invitation = await original_scalar(*args, **kwargs)
                arrivals += 1
                if arrivals == 2:
                    ready.set()
                await asyncio.wait_for(ready.wait(), timeout=10)
                return invitation

            monkeypatch.setattr(db, "scalar", read_invitation)
            try:
                return await OrganizationService(db).accept(payload)
            except HTTPException as exc:
                return exc.status_code

    results = await asyncio.wait_for(asyncio.gather(attempt(), attempt()), timeout=20)
    assert sum(isinstance(result, int) and result == 400 for result in results) == 1
    async with db_factory() as db:
        assert len((await db.scalars(select(Membership))).all()) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["full_name", "tenant_name"])
async def test_registration_rejects_blank_names(client, field):
    from tests.api.test_auth import REGISTER_PAYLOAD

    response = await client.post("/api/v1/auth/register", json={**REGISTER_PAYLOAD, field: "   "})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invitation_cannot_assign_owner_or_choose_another_tenant(client):
    owner = await register_user(client)
    for payload in (
        {"email": "new@example.com", "role": "owner"},
        {"email": "new@example.com", "role": "member", "tenant_id": owner["user"]["tenant"]["id"]},
    ):
        response = await client.post(f"{PREFIX}/invitations", headers=bearer(owner), json=payload)
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_acceptance_cannot_move_an_existing_account(client, db_factory):
    owner = await register_user(client)
    invitation = await client.post(
        f"{PREFIX}/invitations",
        headers=bearer(owner),
        json={
            "email": "new@example.com",
            "role": "member",
        },
    )
    other = await register_user(client, email="new@example.com", tenant_name="Other")
    response = await client.post(
        "/api/v1/organizations/invitations/accept",
        json={
            "token": invitation.json()["token"],
            "full_name": "Attempt",
            "password": "correct-horse",
        },
    )
    assert response.status_code == 409
    me = await client.get("/api/v1/users/me", headers=bearer(other))
    assert me.json()["tenant"]["id"] == other["user"]["tenant"]["id"]
    assert len((await client.get(f"{PREFIX}/members", headers=bearer(owner))).json()) == 1
    async with db_factory() as db:
        invite = (await db.execute(select(Invitation))).scalar_one()
        assert invite.consumed_at is None
