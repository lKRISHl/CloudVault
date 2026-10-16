"""DB-operator-only quota diagnosis/plan change; no public entitlement escalation."""

import argparse
import asyncio
import json
from uuid import UUID

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models import StorageQuota, Tenant
from app.services.quotas import QuotaService


async def run(tenant_id, *, plan=None, limit_bytes=None, apply=False, confirmation=None):
    async with async_session_maker() as db:
        if apply:
            if confirmation != tenant_id or plan not in ("free", "team"):
                raise ValueError("A plan and matching tenant confirmation are required")
            if limit_bytes is not None and not 0 <= limit_bytes <= 9007199254740991:
                raise ValueError("Invalid quota limit")
            tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
            if tenant is None:
                raise ValueError("Workspace not found")
            quota = await db.get(StorageQuota, tenant_id)
            if quota is None:
                quota = StorageQuota(tenant_id=tenant_id)
                db.add(quota)
            quota.storage_plan, quota.storage_limit_bytes = plan, limit_bytes
            await db.commit()
        elif plan is not None or limit_bytes is not None:
            raise ValueError("Plan changes require --apply and --confirm-tenant")
        return (await QuotaService(db).usage(tenant_id)).model_dump()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", type=UUID, required=True)
    parser.add_argument("--plan", choices=("free", "team"))
    parser.add_argument("--limit-bytes", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-tenant", type=UUID)
    args = parser.parse_args()
    try:
        result = asyncio.run(
            run(
                args.tenant,
                plan=args.plan,
                limit_bytes=args.limit_bytes,
                apply=args.apply,
                confirmation=args.confirm_tenant,
            )
        )
    except Exception:
        raise SystemExit("Quota operation failed; verify arguments and database access") from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
