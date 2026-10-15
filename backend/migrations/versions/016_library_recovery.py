"""Durable original-upload cancellation and legacy metadata discard."""

import sqlalchemy as sa
from alembic import op

revision = "016_library_recovery"
down_revision = "015_version_transfers"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("files") as batch:
        batch.add_column(
            sa.Column("upload_cancelled_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.drop_constraint("ck_files_cleanup", type_="check")
        batch.create_check_constraint(
            "ck_files_cleanup",
            "upload_cleanup_at IS NULL OR (status = 'pending' AND "
            "(object_id IS NOT NULL OR upload_cancelled_at IS NOT NULL))",
        )
        batch.create_check_constraint(
            "ck_files_cancelled", "upload_cancelled_at IS NULL OR status = 'pending'"
        )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM files WHERE upload_cancelled_at IS NOT NULL")
    ):
        raise RuntimeError(
            "Original cancellation/discard history cannot be represented; restore a backup"
        )
    with op.batch_alter_table("files") as batch:
        batch.drop_constraint("ck_files_cancelled", type_="check")
        batch.drop_constraint("ck_files_cleanup", type_="check")
        batch.create_check_constraint(
            "ck_files_cleanup",
            "upload_cleanup_at IS NULL OR (status = 'pending' AND object_id IS NOT NULL)",
        )
        batch.drop_column("upload_cancelled_at")
