"""Private resource visibility and membership-bound viewer/editor grants."""

import sqlalchemy as sa
from alembic import op

revision = "012_permissions"
down_revision = "011_sharing"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("folders", "files"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column("visibility", sa.String(16), server_default="workspace", nullable=False)
            )
            batch.create_check_constraint(
                f"ck_{table}_visibility", "visibility IN ('workspace', 'private')"
            )
    op.create_table(
        "resource_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("files.id", ondelete="CASCADE")),
        sa.Column("folder_id", sa.Uuid(), sa.ForeignKey("folders.id", ondelete="CASCADE")),
        sa.Column("role", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            ondelete="CASCADE",
            name="fk_grant_membership",
        ),
        sa.CheckConstraint("role IN ('viewer', 'editor')", name="ck_grant_role"),
        sa.CheckConstraint("(file_id IS NULL) <> (folder_id IS NULL)", name="ck_grant_resource"),
    )
    for kind in ("file", "folder"):
        predicate = sa.text(f"{kind}_id IS NOT NULL")
        op.create_index(
            f"uq_grant_{kind}",
            "resource_grants",
            [f"{kind}_id", "user_id"],
            unique=True,
            postgresql_where=predicate,
            sqlite_where=predicate,
        )
    op.create_index("ix_grant_actor", "resource_grants", ["tenant_id", "user_id"])


def downgrade():
    conn = op.get_bind()
    if conn.scalar(sa.text("SELECT count(*) FROM resource_grants")) or any(
        conn.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE visibility <> 'workspace'"))
        for table in ("files", "folders")
    ):
        raise RuntimeError("Private visibility or grants exist; restore a pre-upgrade backup")
    op.drop_table("resource_grants")
    for table in ("files", "folders"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"ck_{table}_visibility", type_="check")
            batch.drop_column("visibility")
