"""Seed historical schemas without relying on today's evolving ORM/services."""

from types import SimpleNamespace
from uuid import uuid4

import sqlalchemy as sa


async def seed_folder(db, actor, name, parent_id=None):
    folder_id = uuid4()
    table = sa.table(
        "folders",
        *[sa.column(key, sa.Uuid()) for key in ("id", "tenant_id", "parent_id", "created_by")],
        sa.column("name", sa.String()),
        sa.column("name_key", sa.String()),
    )
    await db.execute(
        table.insert().values(
            id=folder_id,
            tenant_id=actor.tenant_id,
            parent_id=parent_id,
            created_by=actor.id,
            name=name,
            name_key=name.casefold(),
        )
    )
    await db.commit()
    return SimpleNamespace(id=folder_id)


async def seed_file(db, tid, uid, fid, name, size):
    table = sa.table(
        "files",
        *[sa.column(key, sa.Uuid()) for key in ("id", "tenant_id", "created_by")],
        sa.column("name", sa.String()),
        sa.column("name_key", sa.String()),
        sa.column("declared_size_bytes", sa.BigInteger()),
    )
    await db.execute(
        table.insert().values(
            id=fid,
            tenant_id=tid,
            created_by=uid,
            name=name,
            name_key=name.casefold(),
            declared_size_bytes=size,
        )
    )
