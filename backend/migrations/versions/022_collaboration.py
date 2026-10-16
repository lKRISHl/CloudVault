"""Folder/named-recipient links, creation retries and separate management ownership."""

import sqlalchemy as sa
from alembic import op

revision = "022_collaboration"
down_revision = "021_storage_quotas"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("share_links") as batch:
        batch.alter_column("file_id", existing_type=sa.Uuid(), nullable=True)
        batch.add_column(sa.Column("folder_id", sa.Uuid()))
        batch.add_column(sa.Column("recipient_email", sa.String(320)))
        batch.add_column(sa.Column("request_id", sa.Uuid()))
        batch.add_column(sa.Column("request_fingerprint", sa.String(64)))
        batch.create_foreign_key(
            "fk_share_folder", "folders", ["folder_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_check_constraint(
            "ck_share_resource", "(file_id IS NULL) <> (folder_id IS NULL)"
        )
        batch.create_unique_constraint(
            "uq_share_request", ["tenant_id", "created_by", "request_id"]
        )
        batch.create_index("ix_share_folder", ["tenant_id", "folder_id", "created_at", "id"])
    op.create_table(
        "resource_owners",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("files.id", ondelete="CASCADE")),
        sa.Column("folder_id", sa.Uuid(), sa.ForeignKey("folders.id", ondelete="CASCADE")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.CheckConstraint("(file_id IS NULL) <> (folder_id IS NULL)", name="ck_owner_resource"),
        sa.UniqueConstraint("file_id", name="uq_owner_file"),
        sa.UniqueConstraint("folder_id", name="uq_owner_folder"),
    )

    op.create_table(
        "workspace_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_key", sa.String(768), nullable=False),
        sa.UniqueConstraint("id", "tenant_id", name="uq_group_tenant"),
        sa.UniqueConstraint("tenant_id", "name_key", name="uq_group_name"),
    )
    op.create_table(
        "group_members",
        sa.Column("group_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id", "tenant_id"],
            ["workspace_groups.id", "workspace_groups.tenant_id"],
            ondelete="CASCADE",
            name="fk_group_member_group",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            ondelete="CASCADE",
            name="fk_group_member_membership",
        ),
    )
    op.create_index("ix_group_member_actor", "group_members", ["tenant_id", "user_id"])
    op.create_table(
        "group_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("files.id", ondelete="CASCADE")),
        sa.Column("folder_id", sa.Uuid(), sa.ForeignKey("folders.id", ondelete="CASCADE")),
        sa.Column("role", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id", "tenant_id"],
            ["workspace_groups.id", "workspace_groups.tenant_id"],
            ondelete="CASCADE",
            name="fk_group_grant_group",
        ),
        sa.CheckConstraint("role IN ('viewer','editor')", name="ck_group_grant_role"),
        sa.CheckConstraint(
            "(file_id IS NULL) <> (folder_id IS NULL)", name="ck_group_grant_resource"
        ),
        sa.UniqueConstraint("file_id", "group_id", name="uq_group_grant_file"),
        sa.UniqueConstraint("folder_id", "group_id", name="uq_group_grant_folder"),
    )
    op.create_index("ix_group_grant_actor", "group_grants", ["tenant_id", "group_id"])


def downgrade():
    connection = op.get_bind()
    if (
        connection.scalar(sa.text("SELECT count(*) FROM workspace_groups"))
        or connection.scalar(sa.text("SELECT count(*) FROM resource_owners"))
        or connection.scalar(
            sa.text(
                "SELECT count(*) FROM share_links WHERE folder_id IS NOT NULL OR recipient_email IS NOT NULL OR request_id IS NOT NULL"
            )
        )
    ):
        raise RuntimeError(
            "Collaboration state cannot be represented by the old schema; restore a coordinated backup"
        )
    op.drop_table("group_grants")
    op.drop_table("group_members")
    op.drop_table("workspace_groups")
    op.drop_table("resource_owners")
    with op.batch_alter_table("share_links") as batch:
        batch.drop_index("ix_share_folder")
        batch.drop_constraint("uq_share_request", type_="unique")
        batch.drop_constraint("ck_share_resource", type_="check")
        batch.drop_constraint("fk_share_folder", type_="foreignkey")
        for column in ("request_fingerprint", "request_id", "recipient_email", "folder_id"):
            batch.drop_column(column)
        batch.alter_column("file_id", existing_type=sa.Uuid(), nullable=False)
