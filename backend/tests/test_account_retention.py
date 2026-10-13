from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest

from app.jobs.deliver_email import cleanup_account_records
from app.models import RefreshToken
from app.models.account import AccountToken, EmailOutbox, LoginSession, RateLimit
from app.services.email import queue_email
from tests.api.test_auth import register_user


@pytest.mark.asyncio
async def test_retention_removes_expired_records_and_keeps_active_sessions(client, db_factory):
    owner = await register_user(client)
    user_id = UUID(owner["user"]["id"])
    current_sid = UUID(
        jwt.decode(owner["access_token"], options={"verify_signature": False})["sid"]
    )
    old = datetime.now(UTC) - timedelta(days=45)
    async with db_factory() as db:
        session = LoginSession(user_id=user_id, expires_at=old)
        db.add(session)
        await db.flush()
        refresh = RefreshToken(
            user_id=user_id, session_id=session.id, token_hash="x" * 64, expires_at=old
        )
        token = AccountToken(
            user_id=user_id,
            purpose="reset",
            email="owner@example.com",
            token_hash="y" * 64,
            expires_at=old,
        )
        counter = RateLimit(key="z" * 64, hits=1, expires_at=old)
        mail = queue_email(db, user_id, "notification", "owner@example.com", "Old", "Old message")
        mail.created_at = old
        db.add_all([refresh, token, counter])
        await db.commit()
        obsolete_ids = session.id, refresh.id, token.id, mail.id
        await cleanup_account_records(db)
    async with db_factory() as db:
        for model, identity in zip(
            (LoginSession, RefreshToken, AccountToken, EmailOutbox), obsolete_ids, strict=True
        ):
            assert await db.get(model, identity) is None
        assert await db.get(RateLimit, "z" * 64) is None
        assert await db.get(LoginSession, current_sid) is not None
