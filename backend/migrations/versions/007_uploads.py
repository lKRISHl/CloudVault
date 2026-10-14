"""Persist upload grants and verified object metadata without storing bytes."""

import sqlalchemy as sa
from alembic import op

revision = "007_uploads"
down_revision = "006_files"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("files") as batch:
        batch.drop_constraint("ck_files_status", type_="check")
        batch.add_column(sa.Column("object_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("storage_bucket", sa.String(63), nullable=True))
        batch.add_column(sa.Column("upload_request_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("expected_checksum_sha256", sa.String(44), nullable=True))
        batch.add_column(sa.Column("size_bytes", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("checksum_sha256", sa.String(44), nullable=True))
        batch.add_column(sa.Column("content_type", sa.String(255), nullable=True))
        batch.add_column(sa.Column("storage_etag", sa.String(255), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint("ck_files_status", "status IN ('pending', 'uploaded')")
        batch.create_check_constraint(
            "ck_files_upload_reference",
            "(object_id IS NULL AND storage_bucket IS NULL AND upload_expires_at IS NULL "
            "AND expected_checksum_sha256 IS NULL AND upload_request_id IS NULL) OR "
            "(object_id IS NOT NULL AND storage_bucket IS NOT NULL "
            "AND upload_expires_at IS NOT NULL "
            "AND expected_checksum_sha256 IS NOT NULL AND upload_request_id IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_files_verified_upload",
            "(status = 'pending' AND size_bytes IS NULL AND checksum_sha256 IS NULL "
            "AND content_type IS NULL AND storage_etag IS NULL AND completed_at IS NULL) OR "
            "(status = 'uploaded' AND object_id IS NOT NULL AND size_bytes IS NOT NULL "
            "AND size_bytes = declared_size_bytes AND checksum_sha256 IS NOT NULL "
            "AND checksum_sha256 = expected_checksum_sha256 "
            "AND content_type IS NOT NULL AND content_type = 'application/octet-stream' "
            "AND storage_etag IS NOT NULL "
            "AND completed_at IS NOT NULL)",
        )
        batch.create_unique_constraint("uq_files_storage_object", ["storage_bucket", "object_id"])
        batch.create_unique_constraint(
            "uq_files_upload_request", ["tenant_id", "created_by", "upload_request_id"]
        )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT id FROM files WHERE object_id IS NOT NULL OR status <> 'pending' LIMIT 1"
            )
        )
        .first()
    ):
        raise RuntimeError("Cannot downgrade upload data safely; restore a pre-upgrade backup")
    with op.batch_alter_table("files") as batch:
        for name in ("uq_files_upload_request", "uq_files_storage_object"):
            batch.drop_constraint(name, type_="unique")
        for name in ("ck_files_verified_upload", "ck_files_upload_reference", "ck_files_status"):
            batch.drop_constraint(name, type_="check")
        for name in (
            "object_id",
            "storage_bucket",
            "upload_request_id",
            "upload_expires_at",
            "expected_checksum_sha256",
            "size_bytes",
            "checksum_sha256",
            "content_type",
            "storage_etag",
            "completed_at",
        ):
            batch.drop_column(name)
        batch.create_check_constraint("ck_files_status", "status = 'pending'")
