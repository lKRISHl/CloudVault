"""Track checksummed multipart uploads without storing file bytes."""

import sqlalchemy as sa
from alembic import op

revision = "008_multipart"
down_revision = "007_uploads"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("files") as batch:
        batch.add_column(
            sa.Column("upload_method", sa.String(16), server_default="basic", nullable=False)
        )
        batch.add_column(
            sa.Column("checksum_kind", sa.String(32), server_default="sha256", nullable=False)
        )
        batch.add_column(sa.Column("multipart_upload_id", sa.String(1024), nullable=True))
        batch.add_column(sa.Column("multipart_part_size", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("multipart_count", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("multipart_state", sa.String(16), nullable=True))
        batch.create_check_constraint(
            "ck_files_transfer_mode",
            "(upload_method = 'basic' AND checksum_kind = 'sha256' AND multipart_upload_"
            "id IS NULL AND multipart_part_size IS NULL AND multipart_count IS NULL AND "
            "multipart_state IS NULL) OR (upload_method = 'multipart' AND checksum_kind "
            "= 'sha256-composite' AND object_id IS NOT NULL AND multipart_upload_id IS N"
            "OT NULL AND length(multipart_upload_id) > 0 AND multipart_part_size IS NOT "
            "NULL AND multipart_part_size BETWEEN 5242880 AND 33554432 AND multipart_cou"
            "nt IS NOT NULL AND multipart_count BETWEEN 1 AND 1024 AND multipart_state I"
            "S NOT NULL AND ((status = 'pending' AND multipart_state IN ('active','abort"
            "ed')) OR (status = 'uploaded' AND multipart_state = 'completed')))",
        )
    op.create_table(
        "upload_parts",
        sa.Column(
            "file_id", sa.Uuid(), sa.ForeignKey("files.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(44), nullable=False),
        sa.Column("storage_etag", sa.String(255), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("number BETWEEN 1 AND 1024", name="ck_upload_parts_number"),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 33554432", name="ck_upload_parts_size"),
        sa.CheckConstraint(
            "(storage_etag IS NULL AND confirmed_at IS NULL) OR (storage_etag IS NOT NUL"
            "L AND confirmed_at IS NOT NULL)",
            name="ck_upload_parts_receipt",
        ),
    )


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT id FROM files WHERE upload_method <> 'basic' LIMIT 1"))
        .first()
    ):
        raise RuntimeError("Cannot discard multipart records; restore a pre-upgrade backup")
    op.drop_table("upload_parts")
    with op.batch_alter_table("files") as batch:
        batch.drop_constraint("ck_files_transfer_mode", type_="check")
        for name in (
            "upload_method",
            "checksum_kind",
            "multipart_upload_id",
            "multipart_part_size",
            "multipart_count",
            "multipart_state",
        ):
            batch.drop_column(name)
