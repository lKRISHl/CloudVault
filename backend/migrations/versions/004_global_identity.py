"""Separate global identity from workspace membership; preserve existing sessions."""

import sqlalchemy as sa
from alembic import op

revision = "004_workspaces"
down_revision = "003_accounts"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("memberships") as batch:
        batch.drop_constraint("fk_memberships_user_tenant", type_="foreignkey")
        batch.drop_constraint("uq_memberships_user", type_="unique")
        batch.create_foreign_key(
            "fk_memberships_user", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_foreign_key(
            "fk_memberships_tenant", "tenants", ["tenant_id"], ["id"], ondelete="CASCADE"
        )
        batch.add_column(sa.Column("revoked_at", sa.DateTime(timezone=True)))
    # Phase 2 removed memberships by deleting the row and disabling the identity.
    # Preserve that removal as a tombstone; recovery must not grant workspace access.
    op.execute(
        sa.text(
            "INSERT INTO memberships (tenant_id, user_id, role, joined_at, revoked_at) "
            "SELECT u.tenant_id, u.id, u.role, u.created_at, CURRENT_TIMESTAMP FROM users u "
            "WHERE u.is_active = false AND u.deleted_at IS NULL AND NOT EXISTS "
            "(SELECT 1 FROM memberships m WHERE m.user_id = u.id)"
        )
    )
    op.execute(
        sa.text(
            "UPDATE login_sessions SET revoked_at = CURRENT_TIMESTAMP "
            "WHERE user_id IN (SELECT id FROM users WHERE is_active = false)"
        )
    )
    op.execute(
        sa.text(
            "UPDATE users SET is_active = true WHERE is_active = false AND deleted_at IS NULL "
            "AND EXISTS (SELECT 1 FROM memberships m WHERE m.user_id = users.id "
            "AND m.revoked_at IS NOT NULL)"
        )
    )
    with op.batch_alter_table("invitations") as batch:
        batch.drop_constraint("fk_invitations_issuer_tenant", type_="foreignkey")
        batch.add_column(
            sa.Column("reactivation", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("invitations") as batch:
        batch.alter_column("reactivation", server_default=None)
    with op.batch_alter_table("login_sessions") as batch:
        batch.add_column(sa.Column("tenant_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_login_sessions_tenant", "tenants", ["tenant_id"], ["id"])
        batch.create_index("ix_login_sessions_tenant_id", ["tenant_id"])
    op.execute(
        sa.text(
            "UPDATE login_sessions SET tenant_id = "
            "(SELECT tenant_id FROM users WHERE users.id = login_sessions.user_id)"
        )
    )
    foreign_key = next(
        item["name"]
        for item in sa.inspect(op.get_bind()).get_foreign_keys("users")
        if item["constrained_columns"] == ["tenant_id"]
    )
    with op.batch_alter_table(
        "users",
        naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
    ) as batch:
        batch.drop_constraint(foreign_key or "fk_users_tenant_id_tenants", type_="foreignkey")
        batch.drop_constraint("uq_users_id_tenant", type_="unique")
        batch.drop_index("ix_users_tenant_id")
        batch.drop_column("tenant_id")
        batch.drop_column("role")
    op.create_index(
        "uq_memberships_active_owner",
        "memberships",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner' AND revoked_at IS NULL"),
        sqlite_where=sa.text("role = 'owner' AND revoked_at IS NULL"),
    )


def downgrade():
    # Never silently discard additional memberships or workspace-less identities.
    unsafe = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT u.id FROM users u LEFT JOIN memberships m ON u.id = m.user_id "
                "GROUP BY u.id HAVING COUNT(m.user_id) <> 1"
            )
        )
        .first()
    )
    if unsafe:
        raise RuntimeError(
            "Cannot downgrade multi-workspace identities safely; restore a pre-upgrade backup"
        )
    cross_issuer = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT i.id FROM invitations i WHERE NOT EXISTS "
                "(SELECT 1 FROM memberships m WHERE m.user_id = i.created_by "
                "AND m.tenant_id = i.tenant_id)"
            )
        )
        .first()
    )
    if cross_issuer:
        raise RuntimeError("Cannot downgrade cross-workspace invitation history safely")
    op.drop_index("uq_memberships_active_owner", table_name="memberships")
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("tenant_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("role", sa.String(20), nullable=True))
    op.execute(
        sa.text(
            "UPDATE users SET tenant_id = "
            "(SELECT tenant_id FROM memberships WHERE memberships.user_id = users.id), "
            "role = (SELECT role FROM memberships WHERE memberships.user_id = users.id)"
        )
    )
    op.execute(
        sa.text(
            "UPDATE users SET is_active = false WHERE id IN "
            "(SELECT user_id FROM memberships WHERE revoked_at IS NOT NULL)"
        )
    )
    with op.batch_alter_table("users") as batch:
        batch.alter_column("tenant_id", nullable=False)
        batch.alter_column("role", nullable=False)
        batch.create_foreign_key(
            "fk_users_tenant_id_tenants", "tenants", ["tenant_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index("ix_users_tenant_id", ["tenant_id"])
        batch.create_unique_constraint("uq_users_id_tenant", ["id", "tenant_id"])
    with op.batch_alter_table("login_sessions") as batch:
        batch.drop_index("ix_login_sessions_tenant_id")
        batch.drop_constraint("fk_login_sessions_tenant", type_="foreignkey")
        batch.drop_column("tenant_id")
    with op.batch_alter_table("invitations") as batch:
        batch.drop_column("reactivation")
        batch.create_foreign_key(
            "fk_invitations_issuer_tenant",
            "users",
            ["created_by", "tenant_id"],
            ["id", "tenant_id"],
        )
    op.execute(sa.text("DELETE FROM memberships WHERE revoked_at IS NOT NULL"))
    with op.batch_alter_table("memberships") as batch:
        batch.drop_constraint("fk_memberships_user", type_="foreignkey")
        batch.drop_constraint("fk_memberships_tenant", type_="foreignkey")
        batch.drop_column("revoked_at")
        batch.create_unique_constraint("uq_memberships_user", ["user_id"])
        batch.create_foreign_key(
            "fk_memberships_user_tenant",
            "users",
            ["user_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="CASCADE",
        )
