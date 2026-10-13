import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from app.core.config import settings
from app.models import User
from app.models.account import AccountToken, EmailOutbox
from app.services.accounts import AccountService
from app.services.email import mail_cipher, recipient_key
from tests.api.test_auth import REGISTER_PAYLOAD, account_token_from_test_email, register_user
from tests.api.test_organizations import add_member, bearer

ROOT = "/api/v1/account"


@pytest.mark.asyncio
async def test_unverified_account_cannot_use_organization_and_queue_is_encrypted(
    client, db_factory
):
    response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    owner = response.json()
    assert owner["user"]["email_verified"] is False
    assert (
        await client.get("/api/v1/organizations/current", headers=bearer(owner))
    ).status_code == 403
    async with db_factory() as db:
        mail = (await db.scalars(select(EmailOutbox))).one()
        assert "owner@example.com" not in mail.encrypted_payload
        payload = json.loads(mail_cipher().decrypt(mail.encrypted_payload.encode()))
        assert payload["recipient"] == REGISTER_PAYLOAD["email"]
        assert "#purpose=verify&token=" in payload["body"]
        assert "correct-horse" not in payload["body"]
    token = await account_token_from_test_email(REGISTER_PAYLOAD["email"], "verify")
    assert (await client.post(f"{ROOT}/verify", json={"token": token})).status_code == 200
    assert (
        await client.get("/api/v1/organizations/current", headers=bearer(owner))
    ).status_code == 200
    assert (await client.post(f"{ROOT}/verify", json={"token": token})).status_code == 400


@pytest.mark.asyncio
async def test_recovery_is_generic_and_does_not_expose_tokens(client):
    await register_user(client)
    results = []
    for email in (REGISTER_PAYLOAD["email"], "missing@example.com"):
        result = await client.post(
            f"{ROOT}/recovery-request", json={"email": email, "purpose": "reset"}
        )
        assert result.status_code == 202
        results.append(result.json())
        assert "token" not in result.json()
    assert results[0] == results[1]


@pytest.mark.asyncio
async def test_password_reset_revokes_access_and_refresh_and_requires_normal_login(client):
    owner = await register_user(client)
    await client.post(
        f"{ROOT}/recovery-request", json={"email": REGISTER_PAYLOAD["email"], "purpose": "reset"}
    )
    token = await account_token_from_test_email(REGISTER_PAYLOAD["email"], "reset")
    result = await client.post(
        f"{ROOT}/reset-password", json={"token": token, "password": "new-correct-password"}
    )
    assert result.status_code == 200
    assert "access_token" not in result.json()
    assert (await client.get("/api/v1/auth/me", headers=bearer(owner))).status_code == 401
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    assert (
        await client.post(
            f"{ROOT}/reset-password", json={"token": token, "password": "another-password"}
        )
    ).status_code == 400
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER_PAYLOAD["email"], "password": REGISTER_PAYLOAD["password"]},
        )
    ).status_code == 401
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER_PAYLOAD["email"], "password": "new-correct-password"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email_verified"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidity", ["wrong-purpose", "expired", "superseded", "unknown"])
async def test_bad_recovery_tokens_rejected(client, db_factory, invalidity):
    await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    old = await account_token_from_test_email(REGISTER_PAYLOAD["email"], "verify")
    if invalidity == "wrong-purpose":
        result = await client.post(
            f"{ROOT}/reset-password", json={"token": old, "password": "new-password"}
        )
    else:
        if invalidity == "expired":
            async with db_factory() as db:
                await db.execute(
                    update(AccountToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
                )
                await db.commit()
        elif invalidity == "superseded":
            await client.post(
                f"{ROOT}/recovery-request",
                json={"email": REGISTER_PAYLOAD["email"], "purpose": "verify"},
            )
        else:
            old = "x" * 64
        result = await client.post(f"{ROOT}/verify", json={"token": old})
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_email_change_reauth_verification_notifications_and_revocation(client, db_factory):
    owner = await register_user(client)
    request = {"email": "updated@example.com", "password": "wrong"}
    assert (
        await client.post(f"{ROOT}/email-change", headers=bearer(owner), json=request)
    ).status_code == 403
    request["password"] = REGISTER_PAYLOAD["password"]
    assert (
        await client.post(f"{ROOT}/email-change", headers=bearer(owner), json=request)
    ).status_code == 202
    me = await client.get("/api/v1/auth/me", headers=bearer(owner))
    assert me.json()["email"] == REGISTER_PAYLOAD["email"]
    token = await account_token_from_test_email(REGISTER_PAYLOAD["email"], "email_change")
    assert (
        await client.post(
            f"{ROOT}/confirm-email",
            headers=bearer(owner),
            json={"token": token, "password": "wrong"},
        )
    ).status_code == 403
    changed = await client.post(
        f"{ROOT}/confirm-email",
        headers=bearer(owner),
        json={"token": token, "password": REGISTER_PAYLOAD["password"]},
    )
    assert changed.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=bearer(owner))).status_code == 401
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "updated@example.com", "password": REGISTER_PAYLOAD["password"]},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email_verified"] is True
    async with db_factory() as db:
        notifications = (
            await db.scalars(
                select(EmailOutbox).where(
                    EmailOutbox.purpose == "notification",
                    EmailOutbox.encrypted_payload.is_not(None),
                )
            )
        ).all()
        payloads = [
            json.loads(mail_cipher().decrypt(mail.encrypted_payload.encode()))
            for mail in notifications
        ]
        assert any(payload["recipient"] == REGISTER_PAYLOAD["email"] for payload in payloads)


@pytest.mark.asyncio
async def test_email_change_cannot_use_another_account_token_or_duplicate_email(client):
    owner = await register_user(client)
    await client.post(
        f"{ROOT}/email-change",
        headers=bearer(owner),
        json={"email": "updated@example.com", "password": REGISTER_PAYLOAD["password"]},
    )
    token = await account_token_from_test_email(REGISTER_PAYLOAD["email"], "email_change")
    other = await register_user(client, email="other@example.com", tenant_name="Other")
    assert (
        await client.post(
            f"{ROOT}/confirm-email",
            headers=bearer(other),
            json={"token": token, "password": REGISTER_PAYLOAD["password"]},
        )
    ).status_code == 400
    assert (
        await client.post(
            f"{ROOT}/email-change",
            headers=bearer(owner),
            json={"email": "other@example.com", "password": REGISTER_PAYLOAD["password"]},
        )
    ).status_code == 409


@pytest.mark.asyncio
async def test_session_ids_survive_refresh_and_individual_revocation_is_immediate(client):
    owner = await register_user(client)
    initial = jwt.decode(owner["access_token"], options={"verify_signature": False})["sid"]
    refreshed = (await client.post("/api/v1/auth/refresh")).json()
    assert (
        jwt.decode(refreshed["access_token"], options={"verify_signature": False})["sid"] == initial
    )
    second = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER_PAYLOAD["email"], "password": REGISTER_PAYLOAD["password"]},
        )
    ).json()
    sid = jwt.decode(second["access_token"], options={"verify_signature": False})["sid"]
    sessions = (await client.get(f"{ROOT}/sessions", headers=bearer(owner))).json()
    assert len(sessions) == 2
    assert next(row for row in sessions if row["id"] == initial)["current"]
    assert (await client.delete(f"{ROOT}/sessions/{sid}", headers=bearer(owner))).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=bearer(second))).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=bearer(owner))).status_code == 200


@pytest.mark.asyncio
async def test_sessions_are_private_and_all_device_logout_revokes_current_access(client):
    owner = await register_user(client)
    other = await register_user(client, email="other@example.com", tenant_name="Other")
    sid = jwt.decode(other["access_token"], options={"verify_signature": False})["sid"]
    assert (await client.delete(f"{ROOT}/sessions/{sid}", headers=bearer(owner))).status_code == 404
    assert (
        await client.post(f"{ROOT}/sign-out-all", headers=bearer(owner), json={"password": "wrong"})
    ).status_code == 403
    assert (
        await client.post(
            f"{ROOT}/sign-out-all",
            headers=bearer(owner),
            json={"password": REGISTER_PAYLOAD["password"]},
        )
    ).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=bearer(owner))).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=bearer(other))).status_code == 200


@pytest.mark.asyncio
async def test_logout_also_revokes_existing_access_token(client):
    owner = await register_user(client)
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=bearer(owner))).status_code == 401


@pytest.mark.asyncio
async def test_deletion_requires_confirmation_and_keeps_owner_protected(client, db_factory):
    owner = await register_user(client)
    payload = {"password": REGISTER_PAYLOAD["password"], "confirmation": "DELETE"}
    assert (
        await client.request("DELETE", ROOT, headers=bearer(owner), json=payload)
    ).status_code == 409
    member, _ = await add_member(client, owner)
    assert (
        await client.request(
            "DELETE", ROOT, headers=bearer(member), json={**payload, "confirmation": "no"}
        )
    ).status_code == 422
    assert (
        await client.request("DELETE", ROOT, headers=bearer(member), json=payload)
    ).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=bearer(member))).status_code == 401
    async with db_factory() as db:
        deleted = await db.get(User, UUID(member["user"]["id"]))
        assert deleted.deleted_at is not None and not deleted.is_active
        assert deleted.email.endswith("@deleted.invalid") and deleted.full_name == "Deleted account"
        incoming_mail = (
            await db.scalars(
                select(EmailOutbox).where(
                    EmailOutbox.recipient_key == recipient_key("member@example.com"),
                )
            )
        ).all()
        assert incoming_mail and all(mail.encrypted_payload is None for mail in incoming_mail)


@pytest.mark.asyncio
async def test_rate_limits_count_failed_logins_and_unknown_account_recovery(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX", 1)
    for path, payload in (
        ("/api/v1/auth/login", {"email": "missing@example.com", "password": "wrong"}),
        (f"{ROOT}/recovery-request", {"email": "missing@example.com", "purpose": "reset"}),
    ):
        first = await client.post(path, json=payload)
        assert first.status_code in (401, 202)
        second = await client.post(path, json=payload)
        assert second.status_code == 429 and "retry-after" in second.headers


@pytest.mark.asyncio
async def test_delivery_status_has_no_token_payload_and_is_scoped(client):
    owner = await register_user(client)
    other = await register_user(client, email="other@example.com", tenant_name="Other")
    mine = await client.get(f"{ROOT}/email-deliveries", headers=bearer(owner))
    theirs = await client.get(f"{ROOT}/email-deliveries", headers=bearer(other))
    assert mine.status_code == 200 and theirs.status_code == 200
    assert {row["id"] for row in mine.json()}.isdisjoint({row["id"] for row in theirs.json()})
    assert "encrypted_payload" not in mine.text and "token" not in mine.text


@pytest.mark.asyncio
async def test_concurrent_password_reset_has_one_winner(client, db_factory, monkeypatch):
    await register_user(client)
    await client.post(
        f"{ROOT}/recovery-request", json={"email": REGISTER_PAYLOAD["email"], "purpose": "reset"}
    )
    token = await account_token_from_test_email(REGISTER_PAYLOAD["email"], "reset")
    barrier = asyncio.Event()
    arrivals = 0

    async def attempt():
        nonlocal arrivals
        async with db_factory() as db:
            original = db.scalar
            first = True

            async def scalar(*args, **kwargs):
                nonlocal arrivals, first
                result = await original(*args, **kwargs)
                if first:
                    first = False
                    arrivals += 1
                    if arrivals == 2:
                        barrier.set()
                    await asyncio.wait_for(barrier.wait(), timeout=10)
                return result

            monkeypatch.setattr(db, "scalar", scalar)
            try:
                await AccountService(db).reset_password(token, "new-password-after-race")
                return 200
            except HTTPException as exc:
                return exc.status_code

    outcomes = await asyncio.wait_for(asyncio.gather(attempt(), attempt()), timeout=20)
    assert sorted(outcomes) == [200, 400]


@pytest.mark.asyncio
async def test_email_change_conflict_at_confirmation_rolls_back_session_revocation(client):
    owner = await register_user(client)
    await client.post(
        f"{ROOT}/email-change",
        headers=bearer(owner),
        json={
            "email": "taken@example.com",
            "password": REGISTER_PAYLOAD["password"],
        },
    )
    token = await account_token_from_test_email(REGISTER_PAYLOAD["email"], "email_change")
    await register_user(client, email="taken@example.com", tenant_name="Other")
    result = await client.post(
        f"{ROOT}/confirm-email",
        headers=bearer(owner),
        json={
            "token": token,
            "password": REGISTER_PAYLOAD["password"],
        },
    )
    assert result.status_code == 409
    me = await client.get("/api/v1/auth/me", headers=bearer(owner))
    assert me.status_code == 200 and me.json()["email"] == REGISTER_PAYLOAD["email"]
