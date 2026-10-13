import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_

from app.core.database import async_session_maker
from app.models import Invitation, RefreshToken
from app.models.account import AccountToken, EmailOutbox, LoginSession, RateLimit
from app.services.email import deliver_next


async def cleanup_account_records(db):
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    for model, criterion in (
        (RateLimit, RateLimit.expires_at < now),
        (AccountToken, AccountToken.expires_at < cutoff),
        (EmailOutbox, EmailOutbox.created_at < cutoff),
        (RefreshToken, or_(RefreshToken.expires_at < cutoff, RefreshToken.revoked_at < cutoff)),
        (LoginSession, or_(LoginSession.expires_at < cutoff, LoginSession.revoked_at < cutoff)),
        (Invitation, or_(Invitation.expires_at < cutoff, Invitation.consumed_at < cutoff)),
    ):
        await db.execute(
            delete(model).where(criterion).execution_options(synchronize_session=False)
        )
    await db.commit()


async def main():
    while True:
        async with async_session_maker() as db:
            await cleanup_account_records(db)
            delivered = await deliver_next(db)
        if not delivered:
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
