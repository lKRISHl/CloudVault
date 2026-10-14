"""Tenant-isolated pending file metadata, without file bytes."""

import sqlalchemy as sa
from alembic import op

revision = "006_files"
down_revision = "005_folders"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("folder_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_key", sa.String(768), nullable=False),
        sa.Column("declared_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("declared_content_type", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["folder_id", "tenant_id"],
            ["folders.id", "folders.tenant_id"],
            name="fk_files_folder_tenant",
        ),
        sa.CheckConstraint("declared_size_bytes >= 0", name="ck_files_declared_size"),
        sa.CheckConstraint("status = 'pending'", name="ck_files_status"),
        sa.UniqueConstraint("tenant_id", "folder_id", "name_key", name="uq_files_sibling_name"),
    )
    op.create_index(
        "uq_files_root_name",
        "files",
        ["tenant_id", "name_key"],
        unique=True,
        postgresql_where=sa.text("folder_id IS NULL"),
        sqlite_where=sa.text("folder_id IS NULL"),
    )
    op.create_index("ix_files_children", "files", ["tenant_id", "folder_id", "name", "id"])
    op.create_index("ix_files_creator", "files", ["tenant_id", "created_by"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT id FROM files LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade nonempty files safely; restore a pre-upgrade backup")
    op.drop_table("files")
