from sqlalchemy import select

from app.models import File, Folder
from app.schemas.search import FileSearchItem, FileSearchPage, FileSearchQuery
from app.services.accounts import AccountService
from app.services.files import FileService
from app.services.permissions import PermissionService


class FileSearchService:
    def __init__(self, db):
        self.db, self.files = db, FileService(db)

    @staticmethod
    def statement(tenant_id, query: FileSearchQuery, actor=None, role=None):
        statement = (
            select(File, Folder.name)
            .outerjoin(Folder, (Folder.id == File.folder_id) & (Folder.tenant_id == File.tenant_id))
            .where(File.tenant_id == tenant_id, File.upload_cleanup_at.is_(None))
        )
        if actor is not None:
            statement = statement.where(PermissionService.file_read(actor, role))
        if query.scope == "root":
            statement = statement.where(File.folder_id.is_(None))
        elif query.scope == "folder":
            statement = statement.where(File.folder_id == query.folder_id)
        if query.q:
            literal = (
                query.q.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            statement = statement.where(File.name_key.like(f"%{literal}%", escape="\\"))
        for field in ("status", "upload_method", "created_by", "declared_content_type"):
            value = getattr(query, field)
            if value is not None:
                statement = statement.where(getattr(File, field) == value)
        if query.min_bytes is not None:
            statement = statement.where(File.declared_size_bytes >= query.min_bytes)
        if query.max_bytes is not None:
            statement = statement.where(File.declared_size_bytes <= query.max_bytes)
        column = {
            "name": File.name_key,
            "size": File.declared_size_bytes,
            "created_at": File.created_at,
            "updated_at": File.updated_at,
        }[query.sort]
        order = (
            (column.asc(), File.id.asc())
            if query.direction == "asc"
            else (column.desc(), File.id.desc())
        )
        return statement.order_by(*order).offset(query.offset).limit(query.limit + 1)

    async def search(self, actor, query: FileSearchQuery, ip="", *, observe=False):
        if not observe:
            await AccountService(self.db).limit(
                "file-search", ip, str(actor.id), max_identity=1200, max_ip=4800
            )
        role = await self.files.folders.authorize(actor)
        if query.scope == "folder":
            await self.files.folders.ancestors(actor, query.folder_id)
        rows = list(await self.db.execute(self.statement(actor.tenant_id, query, actor, role)))
        await PermissionService(self.db).mark(actor, [file for file, _ in rows[: query.limit]])
        return FileSearchPage(
            items=[
                FileSearchItem(
                    **self.files.read(actor, role, file).model_dump(), folder_name=folder_name
                )
                for file, folder_name in rows[: query.limit]
            ],
            offset=query.offset,
            limit=query.limit,
            has_more=len(rows) > query.limit,
        )
