"""Run regression checks with an owned disposable DB and unique provider-test buckets."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


async def main():
    import asyncpg

    database = "cv_phase17_checks_" + uuid4().hex
    admin = await asyncpg.connect(
        host="127.0.0.1",
        port=5432,
        user="cloudvault",
        password="cloudvault",
        database="postgres",
    )
    await admin.execute(f'CREATE DATABASE "{database}"')
    print("Owned disposable database:", database, flush=True)
    try:
        environment = {
            **os.environ,
            "TEST_DATABASE_URL": f"postgresql+asyncpg://cloudvault:cloudvault@127.0.0.1:5432/{database}",
            "TEST_S3_ENDPOINT": "http://127.0.0.1:9000",
            "TEST_S3_ACCESS_KEY": "minioadmin",
            "TEST_S3_SECRET_KEY": "minioadmin",
        }
        result = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                "-m",
                "pytest",
                *(sys.argv[1:] or ["tests/"]),
                "-q",
                "--tb=short",
            ],
            cwd=ROOT / "backend",
            env=environment,
        )
        return result.returncode
    finally:
        await admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
        await admin.close()
        print("Owned database removed:", database, flush=True)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
