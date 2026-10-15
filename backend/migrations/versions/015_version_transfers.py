"""Durable version multipart candidates, cancellation and pruning policy."""

import sqlalchemy as sa
from alembic import op

revision = "015_version_transfers"
down_revision = "014_versions"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("files") as batch:
        batch.add_column(sa.Column("version_keep_last", sa.Integer()))
        batch.add_column(sa.Column("version_policy_checked_at", sa.DateTime(timezone=True)))
        batch.create_check_constraint(
            "ck_files_version_policy",
            "version_keep_last IS NULL OR version_keep_last BETWEEN 1 AND 1000",
        )
        batch.create_index(
            "ix_files_version_policy",
            ["version_policy_checked_at", "id"],
            postgresql_where=sa.text("version_keep_last IS NOT NULL"),
            sqlite_where=sa.text("version_keep_last IS NOT NULL"),
        )
    with op.batch_alter_table("file_versions") as batch:
        for name in ("cancelled_at", "prune_requested_at", "prune_not_before"):
            batch.add_column(sa.Column(name, sa.DateTime(timezone=True)))
        batch.create_check_constraint(
            "ck_versions_cancelled", "cancelled_at IS NULL OR status = 'pending'"
        )
        batch.create_check_constraint(
            "ck_versions_prune",
            "(prune_requested_at IS NULL AND prune_not_before IS NULL) OR "
            "(status = 'uploaded' AND prune_requested_at IS NOT NULL "
            "AND prune_not_before IS NOT NULL)",
        )
    op.create_table(
        "version_parts",
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("file_versions.id"), primary_key=True),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(44), nullable=False),
        sa.Column("storage_etag", sa.String(255)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("number BETWEEN 1 AND 1024", name="ck_version_parts_number"),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 33554432", name="ck_version_parts_size"),
        sa.CheckConstraint(
            "(storage_etag IS NULL AND confirmed_at IS NULL) OR "
            "(storage_etag IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_version_parts_receipt",
        ),
    )


def downgrade():
    bind = op.get_bind()
    if (
        bind.scalar(sa.text("SELECT count(*) FROM version_parts"))
        or bind.scalar(
            sa.text(
                "SELECT count(*) FROM file_versions WHERE cancelled_at IS NOT NULL "
                "OR prune_requested_at IS NOT NULL"
            )
        )
        or bind.scalar(sa.text("SELECT count(*) FROM files WHERE version_keep_last IS NOT NULL"))
    ):
        raise RuntimeError(
            "Version transfers or pruning history exist; restore a pre-upgrade backup"
        )
    op.drop_table("version_parts")
    with op.batch_alter_table("file_versions") as batch:
        batch.drop_constraint("ck_versions_cancelled", type_="check")
        batch.drop_constraint("ck_versions_prune", type_="check")
        for name in ("cancelled_at", "prune_requested_at", "prune_not_before"):
            batch.drop_column(name)
    with op.batch_alter_table("files") as batch:
        batch.drop_index("ix_files_version_policy")
        batch.drop_constraint("ck_files_version_policy", type_="check")
        batch.drop_column("version_policy_checked_at")
        batch.drop_column("version_keep_last")
