"""Retained-reference quota accounting, plans and bounded provider observations."""

import sqlalchemy as sa
from alembic import op

revision = "021_storage_quotas"
down_revision = "020_malware_scanning"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "storage_quotas",
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("storage_plan", sa.String(16), nullable=False, server_default="free"),
        sa.Column("storage_limit_bytes", sa.BigInteger()),
        sa.Column("quota_inventory", sa.JSON()),
        sa.Column("quota_checked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("storage_plan IN ('free','team')", name="ck_storage_quota_plan"),
        sa.CheckConstraint(
            "storage_limit_bytes IS NULL OR storage_limit_bytes >= 0", name="ck_storage_quota_limit"
        ),
    )
    op.create_index("ix_storage_quotas_quota_checked_at", "storage_quotas", ["quota_checked_at"])
    op.execute(
        sa.text("INSERT INTO storage_quotas(tenant_id,storage_plan) SELECT id,'free' FROM tenants")
    )
    with op.batch_alter_table("upload_intents") as batch:
        batch.add_column(sa.Column("reserved_bytes", sa.BigInteger()))
        batch.add_column(sa.Column("cleaned_at", sa.DateTime(timezone=True)))
        batch.create_check_constraint(
            "ck_intent_reserved_bytes", "reserved_bytes IS NULL OR reserved_bytes >= 0"
        )
    # Unknown historical initialization amounts remain NULL, never guessed as zero.
    op.execute(
        sa.text("""UPDATE upload_intents SET reserved_bytes = (
        SELECT files.declared_size_bytes FROM files
        WHERE files.id = upload_intents.file_id
        AND files.tenant_id = upload_intents.tenant_id
        AND files.object_id = upload_intents.object_id
        AND files.storage_bucket = upload_intents.storage_bucket
    )""")
    )
    with op.batch_alter_table("preview_jobs") as batch:
        batch.add_column(
            sa.Column("reserved_bytes", sa.BigInteger(), nullable=False, server_default="1048576")
        )
        batch.add_column(sa.Column("cleaned_at", sa.DateTime(timezone=True)))
        batch.create_check_constraint(
            "ck_preview_quota_bytes", "reserved_bytes BETWEEN 0 AND 1048576"
        )
    op.create_table(
        "storage_observations",
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("namespace", sa.String(64), primary_key=True),
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("storage_bucket", sa.String(63), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_observation_bytes"),
    )
    op.create_index("ix_storage_observations_checked_at", "storage_observations", ["checked_at"])


def downgrade():
    db = op.get_bind()
    if (
        db.execute(
            sa.text("""SELECT 1 FROM upload_intents i WHERE i.reserved_bytes IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM files f WHERE f.id=i.file_id
                AND f.tenant_id=i.tenant_id AND f.object_id=i.object_id
                AND f.storage_bucket=i.storage_bucket)
            AND NOT EXISTS (SELECT 1 FROM file_versions v WHERE v.file_id=i.file_id
                AND v.tenant_id=i.tenant_id AND v.object_id=i.object_id
                AND v.storage_bucket=i.storage_bucket) LIMIT 1""")
        ).first()
        or db.execute(
            sa.text("""SELECT 1 FROM storage_observations
            WHERE size_bytes IS NULL OR size_bytes > 0 LIMIT 1""")
        ).first()
        or db.execute(
            sa.text("""SELECT 1 FROM storage_quotas WHERE storage_plan <> 'free'
        OR storage_limit_bytes IS NOT NULL LIMIT 1""")
        ).first()
    ):
        raise RuntimeError("Quota rollback would lose retained accounting; restore a backup")
    # Ordinary content references remain in the old schema and can be reconstructed.
    # Earlier quarantine/version/trash rollback guards still run; never remove those refs.
    op.drop_index("ix_storage_observations_checked_at", table_name="storage_observations")
    op.drop_table("storage_observations")
    with op.batch_alter_table("preview_jobs") as batch:
        batch.drop_constraint("ck_preview_quota_bytes", type_="check")
        batch.drop_column("cleaned_at")
        batch.drop_column("reserved_bytes")
    with op.batch_alter_table("upload_intents") as batch:
        batch.drop_constraint("ck_intent_reserved_bytes", type_="check")
        batch.drop_column("cleaned_at")
        batch.drop_column("reserved_bytes")
    op.drop_index("ix_storage_quotas_quota_checked_at", table_name="storage_quotas")
    op.drop_table("storage_quotas")
