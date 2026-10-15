"""Immutable application versions and optimistic current-version changes."""

import sqlalchemy as sa
from alembic import op

revision = "014_versions"
down_revision = "013_trash"
branch_labels = None
depends_on = None

CONTENT = (
    "object_id",
    "storage_bucket",
    "upload_expires_at",
    "declared_size_bytes",
    "declared_content_type",
    "expected_checksum_sha256",
    "size_bytes",
    "checksum_sha256",
    "content_type",
    "storage_etag",
    "completed_at",
    "upload_method",
    "checksum_kind",
    "multipart_upload_id",
    "multipart_part_size",
    "multipart_count",
    "multipart_state",
)


def upgrade():
    with op.batch_alter_table("files") as batch:
        batch.add_column(
            sa.Column("current_version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column("version_generation", sa.Integer(), nullable=False, server_default="1")
        )
    op.create_table(
        "file_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("files.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("base_generation", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        *[
            sa.Column(name, sa.String(length), nullable=nullable)
            for name, length, nullable in (
                ("storage_bucket", 63, False),
                ("declared_content_type", 255, True),
                ("expected_checksum_sha256", 44, False),
                ("checksum_sha256", 44, True),
                ("content_type", 255, True),
                ("storage_etag", 255, True),
                ("upload_method", 16, False),
                ("checksum_kind", 32, False),
                ("multipart_upload_id", 1024, True),
                ("multipart_state", 16, True),
            )
        ],
        sa.Column("declared_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("multipart_part_size", sa.Integer()),
        sa.Column("multipart_count", sa.Integer()),
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        *[
            sa.Column(name, sa.DateTime(timezone=True))
            for name in ("cleaned_at", "checked_at", "purged_at")
        ],
        sa.UniqueConstraint("file_id", "number", name="uq_file_versions_number"),
        sa.UniqueConstraint(
            "tenant_id", "created_by", "request_id", name="uq_file_versions_request"
        ),
        sa.UniqueConstraint("storage_bucket", "object_id", name="uq_file_versions_object"),
        sa.CheckConstraint(
            "number >= 1 AND declared_size_bytes >= 0", name="ck_file_versions_size"
        ),
        sa.CheckConstraint("status IN ('pending', 'uploaded')", name="ck_file_versions_status"),
        sa.CheckConstraint(
            "status = 'pending' OR (size_bytes = declared_size_bytes AND size_bytes IS NOT NULL "
            "AND checksum_sha256 = expected_checksum_sha256 AND checksum_sha256 IS NOT NULL "
            "AND content_type = 'application/octet-stream' AND content_type IS NOT NULL "
            "AND storage_etag IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_file_versions_verified",
        ),
    )
    op.create_index("ix_file_versions_history", "file_versions", ["tenant_id", "file_id", "number"])
    op.create_index(
        "ix_file_versions_cleanup", "file_versions", ["status", "checked_at", "upload_expires_at"]
    )
    op.create_table(
        "file_version_changes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("files.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_version_changes_file", "file_version_changes", ["tenant_id", "file_id", "created_at"]
    )
    # Existing objects retain their identity and upload deadline, including trashed/purged rows.
    names = ", ".join(CONTENT)
    op.execute(
        sa.text(
            "INSERT INTO file_versions (id, tenant_id, file_id, number, base_generation, "
            "created_by, "
            f"request_id, status, created_at, purged_at, {names}) "
            "SELECT id, tenant_id, id, 1, 1, created_by, upload_request_id, 'uploaded', "
            f"completed_at, object_purged_at, {names} FROM files WHERE status = 'uploaded'"
        )
    )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM file_versions WHERE number > 1")) or bind.scalar(
        sa.text("SELECT count(*) FROM file_version_changes")
    ):
        raise RuntimeError(
            "Version history or cleanup references exist; restore a pre-upgrade backup"
        )
    op.drop_table("file_version_changes")
    op.drop_table("file_versions")
    with op.batch_alter_table("files") as batch:
        batch.drop_column("version_generation")
        batch.drop_column("current_version")
