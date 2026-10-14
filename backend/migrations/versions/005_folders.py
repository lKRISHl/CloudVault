"""Tenant-isolated folder hierarchy and sibling names."""

import sqlalchemy as sa
from alembic import op

revision = "005_folders"
down_revision = "004_workspaces"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "folders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_key", sa.String(768), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("id", "tenant_id", name="uq_folders_id_tenant"),
        sa.ForeignKeyConstraint(
            ["parent_id", "tenant_id"],
            ["folders.id", "folders.tenant_id"],
            name="fk_folders_parent_tenant",
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name="ck_folders_not_self_parent"
        ),
        sa.UniqueConstraint("tenant_id", "parent_id", "name_key", name="uq_folders_sibling_name"),
    )
    op.create_index(
        "uq_folders_root_name",
        "folders",
        ["tenant_id", "name_key"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NULL"),
        sqlite_where=sa.text("parent_id IS NULL"),
    )
    op.create_index("ix_folders_children", "folders", ["tenant_id", "parent_id", "name", "id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT id FROM folders LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade nonempty folders safely; restore a pre-upgrade backup")
    op.drop_table("folders")
