"""Durable private preview jobs and retained derivative cleanup references."""

import sqlalchemy as sa
from alembic import op

revision = "019_preview_jobs"
down_revision = "018_intent_cancellation"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("background_jobs") as batch:
        batch.drop_constraint("ck_background_job_name", type_="check")
        batch.create_check_constraint(
            "ck_background_job_name", "name IN ('email', 'storage', 'previews')"
        )
    op.create_table(
        "preview_jobs",
        *[
            sa.Column(name, sa.Uuid(), primary_key=name == "id", nullable=False)
            for name in (
                "id",
                "tenant_id",
                "file_id",
                "version_id",
                "requested_by",
                "request_id",
                "artifact_id",
            )
        ],
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_id", sa.Uuid()),
        *[
            sa.Column(
                name, sa.DateTime(timezone=True), nullable=name in ("lease_until", "checked_at")
            )
            for name in (
                "lease_until",
                "next_attempt_at",
                "expires_at",
                "cleanup_after",
                "checked_at",
            )
        ],
        sa.Column("storage_bucket", sa.String(63), nullable=False),
        sa.Column("namespace", sa.String(64), nullable=False),
        sa.Column("digest", sa.String(64)),
        sa.Column("cleanup_failed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_json", sa.JSON()),
        sa.UniqueConstraint("tenant_id", "requested_by", "request_id", name="uq_preview_request"),
        sa.CheckConstraint(
            "state IN ('queued','running','ready','failed','cancelled')", name="ck_preview_state"
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 3 AND page BETWEEN 0 AND 99", name="ck_preview_bounds"
        ),
    )
    op.create_index(
        "ix_preview_dispatch", "preview_jobs", ["state", "next_attempt_at", "lease_until"]
    )
    op.create_index("ix_preview_cleanup", "preview_jobs", ["cleanup_after", "checked_at"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM preview_jobs")):
        raise RuntimeError("Preview cleanup references cannot be discarded; restore a backup")
    from datetime import UTC, datetime

    jobs = sa.table(
        "background_jobs",
        sa.column("name"),
        sa.column("lease_expires_at", sa.DateTime(timezone=True)),
    )
    if op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(jobs)
        .where(
            jobs.c.name == "previews",
            jobs.c.lease_expires_at > datetime.now(UTC),
        )
    ):
        raise RuntimeError("Stop preview workers and wait for active leases before downgrading")
    op.get_bind().execute(jobs.delete().where(jobs.c.name == "previews"))
    op.drop_table("preview_jobs")
    with op.batch_alter_table("background_jobs") as batch:
        batch.drop_constraint("ck_background_job_name", type_="check")
        batch.create_check_constraint("ck_background_job_name", "name IN ('email', 'storage')")
