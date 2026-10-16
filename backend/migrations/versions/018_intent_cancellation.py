"""Retain initialization location and cancellation across trash/recovery."""

import sqlalchemy as sa
from alembic import op

revision = "018_intent_cancellation"
down_revision = "017_background_jobs"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("upload_intents") as batch:
        batch.add_column(sa.Column("folder_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("scope_recorded", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_upload_intents_folder", ["tenant_id", "folder_id"])


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM upload_intents "
            "WHERE folder_id IS NOT NULL OR cancelled_at IS NOT NULL OR scope_recorded = true"
        )
    ):
        raise RuntimeError(
            "Initialization scope/cancellation cannot be discarded; restore a backup"
        )
    with op.batch_alter_table("upload_intents") as batch:
        batch.drop_index("ix_upload_intents_folder")
        batch.drop_column("cancelled_at")
        batch.drop_column("folder_id")
        batch.drop_column("scope_recorded")
