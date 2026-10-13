"""Account verification, revocable sessions, encrypted email outbox, and rate limits."""

import sqlalchemy as sa
from alembic import op

revision = "003_accounts"
down_revision = "002_memberships"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True)))
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email_verified", server_default=None)
    op.create_table(
        "login_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_login_sessions_user_id", "login_sessions", ["user_id"])
    with op.batch_alter_table("refresh_tokens") as batch:
        batch.add_column(sa.Column("session_id", sa.Uuid()))
        batch.create_foreign_key(
            "fk_refresh_tokens_session",
            "login_sessions",
            ["session_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_index("ix_refresh_tokens_session_id", ["session_id"])
    op.execute(
        sa.text("UPDATE refresh_tokens SET revoked_at = CURRENT_TIMESTAMP WHERE revoked_at IS NULL")
    )
    op.create_table(
        "account_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "purpose IN ('verify', 'reset', 'email_change')", name="ck_account_tokens_purpose"
        ),
    )
    op.create_index("ix_account_tokens_user_id", "account_tokens", ["user_id"])
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("recipient_key", sa.String(64), nullable=False),
        sa.Column("encrypted_payload", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(30)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_email_outbox_user_id", "email_outbox", ["user_id"])
    op.create_index("ix_email_outbox_recipient_key", "email_outbox", ["recipient_key"])
    op.create_table(
        "rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("rate_limits")
    op.drop_table("email_outbox")
    op.drop_table("account_tokens")
    with op.batch_alter_table("refresh_tokens") as batch:
        batch.drop_index("ix_refresh_tokens_session_id")
        batch.drop_constraint("fk_refresh_tokens_session", type_="foreignkey")
        batch.drop_column("session_id")
    op.drop_table("login_sessions")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email_verified")
        batch.drop_column("deleted_at")
