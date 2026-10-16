"""Durable maintenance leases, health and inventory checkpoints."""

import sqlalchemy as sa
from alembic import op

revision = "017_background_jobs"
down_revision = "016_library_recovery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "background_jobs",
        sa.Column("name", sa.String(32), primary_key=True),
        sa.Column("lease_id", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("runs", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("cursor", sa.JSON()),
        sa.CheckConstraint("name IN ('email', 'storage')", name="ck_background_job_name"),
        sa.CheckConstraint("runs >= 0 AND failures >= 0", name="ck_background_job_counts"),
    )


def downgrade():
    from datetime import UTC, datetime

    jobs = sa.table("background_jobs", sa.column("lease_expires_at", sa.DateTime(timezone=True)))
    if op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(jobs)
        .where(jobs.c.lease_expires_at > datetime.now(UTC))
    ):
        raise RuntimeError("Stop job workers and wait for active leases before downgrading")
    # Requires stopped schedulers/workers; no user content is in this table. Losing a cursor
    # restarts bounded inventory from its first page, retaining all actual cleanup refs.
    op.drop_table("background_jobs")
