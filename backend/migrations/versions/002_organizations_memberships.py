"""Add organization memberships and invitations; preserve existing users.

Revision ID: 002_memberships
Revises: 001_auth
"""

import sqlalchemy as sa
from alembic import op

revision = "002_memberships"
down_revision = "001_auth"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.create_unique_constraint("uq_users_id_tenant", ["id", "tenant_id"])
    op.create_table(
        "memberships",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id", "user_id"),
        sa.UniqueConstraint("user_id", name="uq_memberships_user"),
        sa.CheckConstraint("role IN ('owner', 'admin', 'member')", name="ck_memberships_role"),
        sa.ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_memberships_user_tenant",
            ondelete="CASCADE",
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO memberships (tenant_id, user_id, role, joined_at) "
            "SELECT tenant_id, id, role, created_at FROM users WHERE is_active = true"
        )
    )
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["created_by", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_invitations_issuer_tenant",
        ),
        sa.CheckConstraint("role IN ('admin', 'member')", name="ck_invitations_role"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_invitations_tenant_id", "invitations", ["tenant_id"])


def downgrade():
    op.drop_index("ix_invitations_tenant_id", table_name="invitations")
    op.drop_table("invitations")
    op.drop_table("memberships")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_id_tenant", type_="unique")
