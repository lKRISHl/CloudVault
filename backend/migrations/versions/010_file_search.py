"""Index live tenant-scoped file search without changing file data."""

import sqlalchemy as sa
from alembic import op

revision = "010_file_search"
down_revision = "009_upload_cleanup"
branch_labels = None
depends_on = None

FIELDS = [
    ("name", "name_key"),
    ("size", "declared_size_bytes"),
    ("created", "created_at"),
    ("updated", "updated_at"),
]


def upgrade():
    predicate = sa.text("upload_cleanup_at IS NULL")
    for name, field in FIELDS:
        op.create_index(
            f"ix_files_search_{name}",
            "files",
            ["tenant_id", field, "id"],
            postgresql_where=predicate,
            sqlite_where=predicate,
        )
    op.create_index(
        "ix_files_search_status",
        "files",
        ["tenant_id", "status", "name_key", "id"],
        postgresql_where=predicate,
        sqlite_where=predicate,
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.create_index(
            "ix_files_search_trgm",
            "files",
            ["name_key"],
            postgresql_using="gin",
            postgresql_ops={"name_key": "gin_trgm_ops"},
            postgresql_where=predicate,
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("ix_files_search_trgm", table_name="files")
    op.drop_index("ix_files_search_status", table_name="files")
    for name, _ in FIELDS:
        op.drop_index(f"ix_files_search_{name}", table_name="files")
    # pg_trgm may be shared by other tables; never remove the extension on rollback.
