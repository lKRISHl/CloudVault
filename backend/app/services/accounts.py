import asyncio
import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models import Invitation, Membership, RefreshToken, User, UserRole
from app.models.account import AccountToken, EmailOutbox, LoginSession, RateLimit
from app.schemas.accounts import EmailDeliveryRead, SessionRead
from app.services.email import queue_email, recipient_key

GENERIC_RECOVERY = "If an eligible account exists, an email will be queued. Check your inbox."


async def issue_account_token(db: AsyncSession, user: User, purpose: str, email: str) -> None:
    now = datetime.now(UTC)
    await db.execute(
        update(AccountToken)
        .where(
            AccountToken.user_id == user.id,
            AccountToken.purpose == purpose,
            AccountToken.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    await db.execute(
        update(EmailOutbox)
        .where(
            EmailOutbox.user_id == user.id,
            EmailOutbox.purpose == purpose,
            EmailOutbox.sent_at.is_(None),
        )
        .values(encrypted_payload=None, error_code="superseded")
    )
    raw = generate_refresh_token()
    expiry = now + timedelta(minutes=settings.ACCOUNT_TOKEN_EXPIRE_MINUTES)
    db.add(
        AccountToken(
            user_id=user.id,
            purpose=purpose,
            email=email,
            token_hash=hash_refresh_token(raw),
            expires_at=expiry,
        )
    )
    link = f"{settings.FRONTEND_URL.rstrip('/')}/account/action#purpose={purpose}&token={raw}"
    queue_email(
        db,
        user.id,
        purpose,
        email,
        "CloudVault account action",
        f"Complete your {purpose.replace('_', ' ')} request:\n{link}\n"
        "If you did not request this, ignore this email. This link expires shortly.",
        expires_at=expiry,
    )


class AccountService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def limit(
        self,
        category: str,
        ip: str,
        identity: str = "",
        *,
        max_identity: int | None = None,
        max_ip: int | None = None,
    ) -> None:
        now = datetime.now(UTC)
        window = int(now.timestamp()) // settings.RATE_LIMIT_WINDOW_SECONDS
        insert = pg_insert if self.db.bind.dialect.name == "postgresql" else sqlite_insert
        for label, value, maximum in (
            ("ip", ip, max_ip if max_ip is not None else settings.RATE_LIMIT_IP_MAX),
            (
                "account",
                identity.lower(),
                max_identity if max_identity is not None else settings.RATE_LIMIT_MAX,
            ),
        ):
            if not value:
                continue
            key = hmac.new(
                settings.SECRET_KEY.encode(),
                f"{category}:{label}:{value}:{window}".encode(),
                hashlib.sha256,
            ).hexdigest()
            statement = (
                insert(RateLimit)
                .values(
                    key=key,
                    hits=1,
                    expires_at=now + timedelta(seconds=settings.RATE_LIMIT_WINDOW_SECONDS),
                )
                .on_conflict_do_update(
                    index_elements=[RateLimit.key], set_={"hits": RateLimit.hits + 1}
                )
            )
            hits = await self.db.scalar(statement.returning(RateLimit.hits))
            await self.db.commit()
            if hits > maximum:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests; try again later",
                    headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS)},
                )

    async def lock_user(self, user_id: UUID) -> User:
        user = await self.db.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if user is None or not user.is_active or user.deleted_at is not None:
            raise HTTPException(status_code=401, detail="Account unavailable")
        return user

    @staticmethod
    def reauthenticate(user: User, password: str) -> None:
        if not verify_password(password, user.password_hash):
            raise HTTPException(status_code=403, detail="Current password is incorrect")

    async def request_recovery(self, email: str, purpose: str, ip: str) -> None:
        started = time.monotonic()
        await self.limit(purpose, ip, email)
        user = await self.db.scalar(
            select(User).where(User.email == email.lower(), User.is_active.is_(True))
        )
        if user is not None and (purpose != "verify" or not user.email_verified):
            user = await self.lock_user(user.id)
            await issue_account_token(self.db, user, purpose, user.email)
        await self.db.commit()
        await asyncio.sleep(
            max(0, settings.RECOVERY_RESPONSE_SECONDS - (time.monotonic() - started))
        )

    async def claim(
        self, token: str, purpose: str, actor: User | None = None
    ) -> tuple[AccountToken, User]:
        stored = await self.db.scalar(
            select(AccountToken).where(
                AccountToken.token_hash == hash_refresh_token(token),
                AccountToken.purpose == purpose,
            )
        )
        if stored is None or (actor is not None and stored.user_id != actor.id):
            raise HTTPException(status_code=400, detail="Invalid or expired account link")
        user = await self.lock_user(stored.user_id)
        if purpose != "email_change" and stored.email != user.email:
            raise HTTPException(status_code=400, detail="Invalid or expired account link")
        now = datetime.now(UTC)
        claimed = await self.db.scalar(
            update(AccountToken)
            .where(
                AccountToken.id == stored.id,
                AccountToken.consumed_at.is_(None),
                AccountToken.expires_at > now,
            )
            .values(consumed_at=now)
            .returning(AccountToken.id)
            .execution_options(synchronize_session=False)
        )
        if claimed is None:
            await self.db.rollback()
            raise HTTPException(status_code=400, detail="Invalid or expired account link")
        return stored, user

    async def revoke_all(self, user_id: UUID) -> None:
        now = datetime.now(UTC)
        await self.db.execute(
            update(LoginSession).where(LoginSession.user_id == user_id).values(revoked_at=now)
        )
        await self.db.execute(
            update(RefreshToken).where(RefreshToken.user_id == user_id).values(revoked_at=now)
        )

    async def invalidate_links(self, user_id: UUID) -> None:
        await self.db.execute(
            update(AccountToken)
            .where(AccountToken.user_id == user_id)
            .values(consumed_at=datetime.now(UTC))
        )
        await self.db.execute(
            update(EmailOutbox)
            .where(
                EmailOutbox.user_id == user_id,
                EmailOutbox.sent_at.is_(None),
            )
            .values(encrypted_payload=None, error_code="superseded")
        )

    async def verify(self, token: str) -> None:
        _, user = await self.claim(token, "verify")
        user.email_verified = True
        await self.db.commit()

    async def reset_password(self, token: str, password: str) -> None:
        _, user = await self.claim(token, "reset")
        user.password_hash = hash_password(password)
        user.email_verified = True
        await self.revoke_all(user.id)
        await self.invalidate_links(user.id)
        queue_email(
            self.db,
            user.id,
            "notification",
            user.email,
            "CloudVault password changed",
            "Your password was reset and all sessions were revoked. "
            "Sign in with your new password.",
        )
        await self.db.commit()

    async def sessions(self, actor: User, current_id: UUID, offset: int, limit: int):
        records = await self.db.scalars(
            select(LoginSession)
            .where(
                LoginSession.user_id == actor.id,
                LoginSession.revoked_at.is_(None),
                LoginSession.expires_at > datetime.now(UTC),
            )
            .order_by(LoginSession.created_at, LoginSession.id)
            .limit(limit)
            .offset(offset)
        )
        return [
            SessionRead(
                id=row.id,
                created_at=row.created_at,
                expires_at=row.expires_at,
                current=row.id == current_id,
            )
            for row in records
        ]

    async def deliveries(self, actor: User):
        records = await self.db.scalars(
            select(EmailOutbox)
            .where(EmailOutbox.user_id == actor.id)
            .order_by(EmailOutbox.created_at.desc())
            .limit(25)
        )
        return [
            EmailDeliveryRead(
                id=row.id,
                purpose=row.purpose,
                attempts=row.attempts,
                next_attempt_at=row.next_attempt_at,
                state="sent" if row.sent_at else (row.error_code or "queued"),
            )
            for row in records
        ]

    async def request_email_change(self, actor: User, email: str, password: str) -> None:
        user = await self.lock_user(actor.id)
        if not user.email_verified:
            raise HTTPException(status_code=403, detail="Verify your current email first")
        self.reauthenticate(user, password)
        if email.lower() == user.email:
            raise HTTPException(status_code=400, detail="Choose a different email")
        if await self.db.scalar(select(User.id).where(User.email == email.lower())) is not None:
            raise HTTPException(status_code=409, detail="Email is unavailable")
        await issue_account_token(self.db, user, "email_change", email.lower())
        queue_email(
            self.db,
            user.id,
            "notification",
            user.email,
            "CloudVault email change requested",
            "An email change was requested. Your address remains unchanged "
            "until the new address is verified.",
        )
        await self.db.commit()

    async def confirm_email_change(self, actor: User, token: str, password: str) -> None:
        self.reauthenticate(await self.lock_user(actor.id), password)
        stored, user = await self.claim(token, "email_change", actor)
        previous = user.email
        try:
            user.email = stored.email
            user.email_verified = True
            await self.revoke_all(user.id)
            await self.invalidate_links(user.id)
            queue_email(
                self.db,
                user.id,
                "notification",
                previous,
                "CloudVault email changed",
                "Your account email was changed. All sessions were revoked. "
                "Contact support if this was not you.",
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(status_code=409, detail="Email is unavailable") from exc

    async def revoke_session(self, actor: User, session_id: UUID) -> None:
        await self.lock_user(actor.id)
        claimed = await self.db.scalar(
            update(LoginSession)
            .where(
                LoginSession.id == session_id,
                LoginSession.user_id == actor.id,
            )
            .values(revoked_at=datetime.now(UTC))
            .returning(LoginSession.id)
        )
        if claimed is None:
            raise HTTPException(status_code=404, detail="Session not found")
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.session_id == session_id)
            .values(revoked_at=datetime.now(UTC))
        )
        await self.db.commit()

    async def delete_account(self, actor: User, password: str) -> None:
        # Lock every organization in stable order before the global identity.
        from app.models import Tenant

        tenant_ids = select(Membership.tenant_id).where(Membership.user_id == actor.id)
        await self.db.execute(
            select(Tenant).where(Tenant.id.in_(tenant_ids)).order_by(Tenant.id).with_for_update()
        )
        user = await self.lock_user(actor.id)
        self.reauthenticate(user, password)
        if not user.email_verified:
            raise HTTPException(
                status_code=403, detail="Verify your email before deleting your account"
            )
        if (
            await self.db.scalar(
                select(Membership.user_id).where(
                    Membership.user_id == user.id,
                    Membership.role == UserRole.OWNER,
                    Membership.revoked_at.is_(None),
                )
            )
            is not None
        ):
            raise HTTPException(
                status_code=409,
                detail="Transfer organization ownership before deleting your account",
            )
        await self.revoke_all(user.id)
        await self.invalidate_links(user.id)
        await self.db.execute(delete(AccountToken).where(AccountToken.user_id == user.id))
        await self.db.execute(
            update(EmailOutbox)
            .where(
                EmailOutbox.recipient_key == recipient_key(user.email),
                EmailOutbox.sent_at.is_(None),
            )
            .values(encrypted_payload=None, error_code="account_deleted")
        )
        # Verified identity owns this email even across incoming invitations.
        await self.db.execute(
            update(Invitation)
            .where(Invitation.email == user.email)
            .values(
                email=f"deleted-{user.id}@deleted.invalid",
                consumed_at=datetime.now(UTC),
            )
        )
        await self.db.execute(
            update(Invitation)
            .where(Invitation.created_by == user.id)
            .values(consumed_at=datetime.now(UTC))
        )
        from app.models import ShareLink

        await self.db.execute(
            update(ShareLink)
            .where(
                ShareLink.created_by == user.id,
                ShareLink.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await self.db.execute(delete(Membership).where(Membership.user_id == user.id))
        user.is_active = False
        user.deleted_at = datetime.now(UTC)
        user.email = f"deleted-{user.id}@deleted.invalid"
        user.full_name = "Deleted account"
        user.password_hash = hash_password(generate_refresh_token())
        await self.db.commit()
