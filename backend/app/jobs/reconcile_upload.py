"""DB-operator-only legacy inventory/retirement; no public HTTP endpoint."""

import argparse
import asyncio
import json
from uuid import UUID

from app.core.config import settings
from app.core.database import async_session_maker
from app.services.reconciliation import ReconciliationService
from app.storage.s3 import S3ObjectStorage


async def run(
    tenant_id,
    file_id,
    *,
    apply=False,
    confirmation=None,
    version_id=None,
    operator_user=None,
    offset=0,
):
    storage = None
    try:
        async with async_session_maker() as db:
            service = ReconciliationService(db)
            if not apply:
                return await service.diagnose(tenant_id, file_id, offset=offset)
            if confirmation != file_id:
                raise ValueError("Exact file confirmation required")
            storage = S3ObjectStorage(settings, tenant_id)
            service.storage = storage
            if version_id is not None:
                if operator_user is None:
                    raise ValueError("Workspace manager identity required for adoption")
                return {
                    "state": await service.adopt(
                        tenant_id,
                        file_id,
                        version_id,
                        operator_user,
                        confirmed_file_id=confirmation,
                    )
                }
            return {
                "state": await service.retire(
                    tenant_id,
                    file_id,
                    confirmed_file_id=confirmation,
                )
            }
    finally:
        if storage is not None:
            await storage.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", type=UUID, required=True)
    parser.add_argument("--file", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-file", type=UUID)
    parser.add_argument("--adopt-version", type=UUID)
    parser.add_argument("--operator-user", type=UUID)
    parser.add_argument("--version-offset", type=int, default=0)
    args = parser.parse_args()
    try:
        result = asyncio.run(
            run(
                args.tenant,
                args.file,
                apply=args.apply,
                confirmation=args.confirm_file,
                version_id=args.adopt_version,
                operator_user=args.operator_user,
                offset=args.version_offset,
            )
        )
    except Exception:
        print(json.dumps({"state": "refused_or_unavailable", "references_retained": True}))
        raise SystemExit(1) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
