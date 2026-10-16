from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.models import Group, GroupGrant, GroupMember, Membership, User, UserRole
from app.schemas.groups import GroupPage, GroupRead
from app.schemas.permissions import CandidatePage, CandidateRead
from app.services.accounts import AccountService
from app.services.folders import FolderService
from app.services.permissions import PermissionService


class GroupService:
    """Workspace directory groups, with local viewer/editor grants and no role escalation."""

    def __init__(self, db):
        self.db = db

    async def authorize(self, actor, write=False):
        role = await FolderService(self.db).authorize(actor, write=write)
        if role not in (UserRole.OWNER, UserRole.ADMIN):
            raise HTTPException(403, "Workspace manager required to manage groups")

    async def owned(self, actor, group_id):
        group = await self.db.scalar(
            select(Group).where(Group.tenant_id == actor.tenant_id, Group.id == group_id)
        )
        if group is None:
            raise HTTPException(404, "Group not found")
        return group

    async def listing(self, actor, query, offset):
        await FolderService(self.db).authorize(actor)
        rows = list(
            await self.db.scalars(
                select(Group)
                .where(
                    Group.tenant_id == actor.tenant_id,
                    Group.name.icontains(query.strip(), autoescape=True),
                )
                .order_by(Group.name, Group.id)
                .offset(offset)
                .limit(26)
            )
        )
        return GroupPage(
            items=[GroupRead.model_validate(row) for row in rows[:25]],
            offset=offset,
            has_more=len(rows) > 25,
        )

    async def create(self, actor, name, ip):
        await AccountService(self.db).limit(
            "workspace-groups", ip, str(actor.id), max_identity=50, max_ip=200
        )
        await self.authorize(actor, write=True)
        if (
            await self.db.scalar(
                select(func.count()).select_from(Group).where(Group.tenant_id == actor.tenant_id)
            )
            >= 100
        ):
            raise HTTPException(409, "Workspace group limit reached (100)")
        group = Group(tenant_id=actor.tenant_id, name=name, name_key=name.casefold())
        self.db.add(group)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(409, "Group name already exists") from None
        await self.db.refresh(group)
        return GroupRead.model_validate(group)

    async def members(self, actor, group_id, query, offset, candidates=False):
        await self.authorize(actor)
        await self.owned(actor, group_id)
        statement = (
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.tenant_id == actor.tenant_id,
                Membership.revoked_at.is_(None),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.email_verified.is_(True),
                or_(
                    User.full_name.icontains(query.strip(), autoescape=True),
                    User.email.icontains(query.strip(), autoescape=True),
                ),
            )
        )
        if not candidates:
            statement = statement.where(
                User.id.in_(
                    select(GroupMember.user_id).where(
                        GroupMember.tenant_id == actor.tenant_id, GroupMember.group_id == group_id
                    )
                )
            )
        rows = list(
            await self.db.scalars(
                statement.order_by(User.full_name, User.id).offset(offset).limit(26)
            )
        )
        return CandidatePage(
            items=[
                CandidateRead(user_id=row.id, full_name=row.full_name, email=row.email)
                for row in rows[:25]
            ],
            offset=offset,
            has_more=len(rows) > 25,
        )

    async def invalidate(self, actor, group_id):
        # At most100 grants per group; revoke affected roots/subtrees in the same transaction.
        for grant in await self.db.scalars(
            select(GroupGrant).where(
                GroupGrant.tenant_id == actor.tenant_id, GroupGrant.group_id == group_id
            )
        ):
            await PermissionService(self.db).invalidate_shares(
                actor, "files" if grant.file_id else "folders", grant.file_id or grant.folder_id
            )

    async def membership(self, actor, group_id, user_id, present, ip):
        await AccountService(self.db).limit(
            "workspace-groups", ip, str(actor.id), max_identity=100, max_ip=500
        )
        await self.authorize(actor, write=True)
        await self.owned(actor, group_id)
        row = await self.db.get(GroupMember, (group_id, user_id))
        if present:
            eligible = await self.db.scalar(
                select(User.id)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.tenant_id == actor.tenant_id,
                    Membership.revoked_at.is_(None),
                    User.id == user_id,
                    User.is_active.is_(True),
                    User.email_verified.is_(True),
                    User.deleted_at.is_(None),
                )
            )
            if eligible is None:
                raise HTTPException(404, "Eligible workspace member not found")
            if row is None:
                if (
                    await self.db.scalar(
                        select(func.count())
                        .select_from(GroupMember)
                        .where(GroupMember.group_id == group_id)
                    )
                    >= 1000
                ):
                    raise HTTPException(409, "Group membership limit reached (1000)")
                self.db.add(
                    GroupMember(group_id=group_id, user_id=user_id, tenant_id=actor.tenant_id)
                )
                await self.invalidate(actor, group_id)
        elif row is not None:
            await self.db.delete(row)
            await self.invalidate(actor, group_id)
        await self.db.commit()

    async def remove(self, actor, group_id: UUID, ip):
        await AccountService(self.db).limit(
            "workspace-groups", ip, str(actor.id), max_identity=50, max_ip=200
        )
        await self.authorize(actor, write=True)
        await self.owned(actor, group_id)
        await self.invalidate(actor, group_id)
        await self.db.execute(
            delete(GroupGrant).where(
                GroupGrant.tenant_id == actor.tenant_id, GroupGrant.group_id == group_id
            )
        )
        await self.db.execute(
            delete(GroupMember).where(
                GroupMember.tenant_id == actor.tenant_id, GroupMember.group_id == group_id
            )
        )
        await self.db.execute(
            delete(Group).where(Group.tenant_id == actor.tenant_id, Group.id == group_id)
        )
        await self.db.commit()
