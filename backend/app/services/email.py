import asyncio
import base64
import hashlib
import hmac
import json
import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.account import EmailOutbox


def mail_cipher() -> Fernet:
    key = hashlib.sha256(("email-outbox:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def recipient_key(email: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), ("recipient:" + email.lower()).encode(), hashlib.sha256
    ).hexdigest()


def queue_email(
    db: AsyncSession,
    user_id: UUID | None,
    purpose: str,
    recipient: str,
    subject: str,
    body: str,
    expires_at: datetime | None = None,
) -> EmailOutbox:
    payload = json.dumps({"recipient": recipient, "subject": subject, "body": body})
    mail = EmailOutbox(
        user_id=user_id,
        purpose=purpose,
        recipient_key=recipient_key(recipient),
        encrypted_payload=mail_cipher().encrypt(payload.encode()).decode(),
        next_attempt_at=datetime.now(UTC),
        expires_at=expires_at or datetime.now(UTC) + timedelta(days=1),
    )
    db.add(mail)
    return mail


def send_smtp(payload: dict, message_id: UUID) -> None:
    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = payload["recipient"]
    message["Subject"] = payload["subject"]
    message["Message-ID"] = f"<{message_id}@cloudvault>"
    message.set_content(payload["body"])
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls(context=ssl.create_default_context())
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
        refused = smtp.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


async def deliver_next(db: AsyncSession) -> bool:
    now = datetime.now(UTC)
    await db.execute(
        update(EmailOutbox)
        .where(
            EmailOutbox.sent_at.is_(None),
            EmailOutbox.encrypted_payload.is_not(None),
            or_(EmailOutbox.expires_at <= now, EmailOutbox.attempts >= 12),
        )
        .values(encrypted_payload=None, error_code="delivery_expired")
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    eligible = (
        EmailOutbox.sent_at.is_(None),
        EmailOutbox.encrypted_payload.is_not(None),
        EmailOutbox.next_attempt_at <= now,
        EmailOutbox.expires_at > now,
        or_(EmailOutbox.lease_until.is_(None), EmailOutbox.lease_until < now),
    )
    mail = await db.scalar(
        select(EmailOutbox)
        .where(*eligible)
        .order_by(EmailOutbox.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if mail is None:
        await db.rollback()
        return False
    claim = await db.execute(
        update(EmailOutbox)
        .where(EmailOutbox.id == mail.id, *eligible)
        .values(lease_until=now + timedelta(seconds=300), attempts=EmailOutbox.attempts + 1)
        .returning(EmailOutbox.attempts)
        .execution_options(synchronize_session=False)
    )
    attempts = claim.scalar_one_or_none()
    if attempts is None:
        await db.rollback()
        return False
    mail_id, encrypted = mail.id, mail.encrypted_payload
    await db.commit()
    try:
        payload = json.loads(mail_cipher().decrypt(encrypted.encode()))
        await asyncio.to_thread(send_smtp, payload, mail_id)
    except Exception:
        # Never persist exception text: SMTP errors can contain recipient/token content.
        await db.execute(
            update(EmailOutbox)
            .where(EmailOutbox.id == mail_id)
            .values(
                lease_until=None,
                error_code="delivery_failed",
                next_attempt_at=datetime.now(UTC)
                + timedelta(seconds=min(3600, 2 ** min(attempts, 10))),
            )
        )
    else:
        await db.execute(
            update(EmailOutbox)
            .where(EmailOutbox.id == mail_id)
            .values(
                sent_at=datetime.now(UTC),
                lease_until=None,
                error_code=None,
                encrypted_payload=None,
            )
        )
    await db.commit()
    return True
