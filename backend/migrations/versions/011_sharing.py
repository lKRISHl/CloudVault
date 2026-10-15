"""Expiring, revocable file capabilities; never persist raw link secrets."""

import sqlalchemy as sa
from alembic import op

revision = "011_sharing"
down_revision = "010_file_search"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "share_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "file_id", sa.Uuid(), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("allow_download", sa.Boolean(), nullable=False),
        sa.Column("max_downloads", sa.Integer()),
        sa.Column("download_grants", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("download_grants >= 0", name="ck_share_grants"),
        sa.CheckConstraint(
            "max_downloads IS NULL OR max_downloads BETWEEN 1 AND 10000", name="ck_share_max"
        ),
    )
    op.create_index("ix_share_file", "share_links", ["tenant_id", "file_id", "created_at", "id"])


def downgrade():
    # Losing live capabilities would silently revoke externally distributed links.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM share_links")):
        raise RuntimeError("Sharing records exist; restore a pre-upgrade backup for rollback")
    op.drop_table("share_links")
