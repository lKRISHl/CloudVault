"""Retain cleanup tombstones while releasing abandoned upload names."""

import sqlalchemy as sa
from alembic import op

revision = "009_upload_cleanup"
down_revision = "008_multipart"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "upload_intents",
        sa.Column("file_id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("storage_bucket", sa.String(63), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "created_by", "request_id", name="uq_upload_intents_request"
        ),
    )
    op.create_index(
        "ix_upload_intents_cleanup",
        "upload_intents",
        ["storage_bucket", "expires_at", "checked_at"],
    )
    with op.batch_alter_table("files") as batch:
        batch.add_column(sa.Column("upload_cleanup_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("upload_cleanup_checked_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_check_constraint(
            "ck_files_cleanup",
            "upload_cleanup_at IS NULL OR (status = 'pending' AND object_id IS NOT NULL)",
        )
        batch.create_index(
            "ix_files_upload_cleanup",
            ["status", "storage_bucket", "upload_expires_at", "upload_cleanup_checked_at"],
        )
        batch.drop_constraint("uq_files_sibling_name", type_="unique")
        batch.drop_index("uq_files_root_name")
        for name, fields, condition in [
            ("uq_files_root_name", ["tenant_id", "name_key"], "folder_id IS NULL"),
            (
                "uq_files_sibling_name",
                ["tenant_id", "folder_id", "name_key"],
                "folder_id IS NOT NULL",
            ),
        ]:
            predicate = sa.text(condition + " AND upload_cleanup_at IS NULL")
            batch.create_index(
                name, fields, unique=True, postgresql_where=predicate, sqlite_where=predicate
            )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT file_id FROM upload_intents LIMIT 1")).first():
        raise RuntimeError(
            "Cannot discard upload initialization intents; restore a pre-upgrade backup"
        )
    if (
        op.get_bind()
        .execute(sa.text("SELECT id FROM files WHERE upload_cleanup_at IS NOT NULL LIMIT 1"))
        .first()
    ):
        raise RuntimeError("Cannot discard upload cleanup tombstones; restore a pre-upgrade backup")
    with op.batch_alter_table("files") as batch:
        batch.drop_index("ix_files_upload_cleanup")
        batch.drop_index("uq_files_root_name")
        batch.drop_index("uq_files_sibling_name")
        batch.create_unique_constraint(
            "uq_files_sibling_name", ["tenant_id", "folder_id", "name_key"]
        )
        batch.create_index(
            "uq_files_root_name",
            ["tenant_id", "name_key"],
            unique=True,
            postgresql_where=sa.text("folder_id IS NULL"),
            sqlite_where=sa.text("folder_id IS NULL"),
        )
        batch.drop_column("upload_cleanup_checked_at")
        batch.drop_constraint("ck_files_cleanup", type_="check")
        batch.drop_column("upload_cleanup_at")
    op.drop_table("upload_intents")
