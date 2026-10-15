"""Retained trash batches, live names and durable object-purge references."""

import sqlalchemy as sa
from alembic import op

revision = "013_trash"
down_revision = "012_permissions"
branch_labels = None
depends_on = None


def file_names(trashed):
    for suffix, fields, condition in [
        ("root", ["tenant_id", "name_key"], "folder_id IS NULL"),
        ("sibling", ["tenant_id", "folder_id", "name_key"], "folder_id IS NOT NULL"),
    ]:
        predicate = sa.text(
            condition
            + " AND upload_cleanup_at IS NULL"
            + (" AND trash_id IS NULL" if trashed else "")
        )
        op.create_index(
            f"uq_files_{suffix}_name",
            "files",
            fields,
            unique=True,
            postgresql_where=predicate,
            sqlite_where=predicate,
        )


def upgrade():
    op.create_table(
        "trash_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("root_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("trashed_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "trashed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        *[
            sa.Column(name, sa.DateTime(timezone=True))
            for name in ("purge_requested_at", "purged_at", "restored_at", "checked_at")
        ],
        sa.CheckConstraint("kind IN ('files', 'folders')", name="ck_trash_kind"),
    )
    op.create_index("ix_trash_tenant", "trash_entries", ["tenant_id", "trashed_at", "id"])
    op.create_index("ix_trash_maintenance", "trash_entries", ["checked_at", "retain_until"])
    for table in ("folders", "files"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("trash_id", sa.Uuid(), nullable=True))
            batch.create_foreign_key(f"fk_{table}_trash", "trash_entries", ["trash_id"], ["id"])
            batch.create_index(f"ix_{table}_trash_id", ["trash_id"])
            if table == "files":
                batch.add_column(sa.Column("object_purged_at", sa.DateTime(timezone=True)))
                batch.add_column(sa.Column("purge_checked_at", sa.DateTime(timezone=True)))
    for name in ("uq_files_root_name", "uq_files_sibling_name"):
        op.drop_index(name, table_name="files")
    file_names(True)
    with op.batch_alter_table("folders") as batch:
        batch.drop_constraint("uq_folders_sibling_name", type_="unique")
        batch.drop_index("uq_folders_root_name")
        for name, fields, condition in [
            ("uq_folders_root_name", ["tenant_id", "name_key"], "parent_id IS NULL"),
            (
                "uq_folders_sibling_name",
                ["tenant_id", "parent_id", "name_key"],
                "parent_id IS NOT NULL",
            ),
        ]:
            predicate = sa.text(condition + " AND trash_id IS NULL")
            batch.create_index(
                name, fields, unique=True, postgresql_where=predicate, sqlite_where=predicate
            )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM trash_entries")):
        raise RuntimeError("Trash history or purge references exist; restore a pre-upgrade backup")
    for name in ("uq_files_root_name", "uq_files_sibling_name"):
        op.drop_index(name, table_name="files")
    file_names(False)
    with op.batch_alter_table("folders") as batch:
        batch.drop_index("uq_folders_root_name")
        batch.drop_index("uq_folders_sibling_name")
        batch.create_unique_constraint(
            "uq_folders_sibling_name", ["tenant_id", "parent_id", "name_key"]
        )
        batch.create_index(
            "uq_folders_root_name",
            ["tenant_id", "name_key"],
            unique=True,
            postgresql_where=sa.text("parent_id IS NULL"),
            sqlite_where=sa.text("parent_id IS NULL"),
        )
    for table in ("files", "folders"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_trash", type_="foreignkey")
            batch.drop_index(f"ix_{table}_trash_id")
            batch.drop_column("trash_id")
            if table == "files":
                batch.drop_column("object_purged_at")
                batch.drop_column("purge_checked_at")
    op.drop_table("trash_entries")
