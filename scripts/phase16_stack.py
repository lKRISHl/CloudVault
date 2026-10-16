"""Own one isolated Phase 16 acceptance stack; never target application DBs/volumes."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".local" / "phase16-stack.json"


def compose(project, *args, **kwargs):
    if not re.fullmatch(r"cv-phase16-check-[0-9a-f]{12}", project):
        raise ValueError("Refusing an unowned acceptance project")
    return subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            str(ROOT / "infra/testing/phase16.compose.yml"),
            *args,
        ],
        cwd=ROOT,
        check=True,
        **kwargs,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("up", "status", "suite", "migrations", "down")
    )
    parser.add_argument(
        "tests", nargs="*", help="Optional test paths for the disposable suite"
    )
    args = parser.parse_args()
    if args.action == "up":
        if MANIFEST.exists():
            raise RuntimeError(
                "An owned acceptance manifest already exists; inspect it first"
            )
        project = "cv-phase16-check-" + uuid4().hex[:12]
        # Write before starting so partial build/start failures remain discoverable.
        MANIFEST.parent.mkdir(exist_ok=True)
        MANIFEST.write_text(
            json.dumps({"project": project, "root": str(ROOT)}, indent=2)
        )
        compose(project, "up", "--build", "-d", "--wait", "--wait-timeout", "180")
        print("Owned acceptance UI: http://127.0.0.1:43916")
        return
    manifest = json.loads(MANIFEST.read_text())
    if manifest["root"] != str(ROOT):
        raise ValueError("Acceptance workspace changed")
    project = manifest["project"]
    if args.action == "status":
        compose(project, "ps")
    elif args.action in ("suite", "migrations"):
        database = "phase16_suite_" + uuid4().hex[:12]
        compose(
            project, "exec", "-T", "postgres", "createdb", "-U", "cloudvault", database
        )
        try:
            if args.action == "migrations":
                url = f"postgresql+asyncpg://cloudvault:cloudvault@postgres:5432/{database}"

                def migrate(*arguments):
                    compose(
                        project,
                        "run",
                        "--rm",
                        "--no-deps",
                        "-e",
                        f"DATABASE_URL={url}",
                        "backend",
                        "python",
                        "-m",
                        "alembic",
                        *arguments,
                    )

                migrate("upgrade", "016_library_recovery")
                identity = uuid4().hex

                def sql(statement):
                    return compose(
                        project,
                        "exec",
                        "-T",
                        "postgres",
                        "psql",
                        "-U",
                        "cloudvault",
                        "-d",
                        database,
                        "-v",
                        "ON_ERROR_STOP=1",
                        "-Atc",
                        statement,
                        capture_output=True,
                        text=True,
                    ).stdout.strip()

                sql(
                    "INSERT INTO upload_intents (file_id,tenant_id,object_id,created_by,request_id,"
                    "storage_bucket,fingerprint,expires_at) VALUES ("
                    + ",".join(
                        "'" + value + "'"
                        for value in [
                            identity,
                            *[uuid4().hex for _ in range(4)],
                            "owned-migration-bucket",
                            "0" * 64,
                            "2026-10-16 12:00:00+00",
                        ]
                    )
                    + ")"
                )
                migrate("upgrade", "head")
                assert (
                    sql(
                        "SELECT scope_recorded=false AND folder_id IS NULL AND cancelled_at IS NULL "
                        f"FROM upload_intents WHERE file_id='{identity}'"
                    )
                    == "t"
                )
                migrate("check")
                migrate("downgrade", "016_library_recovery")
                migrate("upgrade", "head")
                print(
                    "Real PostgreSQL 016–019 upgrade/downgrade/re-upgrade preserved legacy intent"
                )
                return
            environment = {
                **os.environ,
                "TEST_DATABASE_URL": f"postgresql+asyncpg://cloudvault:cloudvault@127.0.0.1:45916/{database}",
                "TEST_S3_ENDPOINT": "http://127.0.0.1:49916",
                "TEST_S3_ACCESS_KEY": "minioadmin",
                "TEST_S3_SECRET_KEY": "minioadmin",
            }
            subprocess.run(
                [sys.executable, "-m", "pytest", *(args.tests or ["tests/"]), "-q"],
                cwd=ROOT / "backend",
                env=environment,
                check=True,
            )
        finally:
            compose(
                project,
                "exec",
                "-T",
                "postgres",
                "dropdb",
                "-U",
                "cloudvault",
                "--force",
                database,
            )
    else:
        # Only resources bearing this unique Compose project are eligible for cleanup.
        compose(project, "down", "--volumes", "--remove-orphans")
        MANIFEST.unlink()


if __name__ == "__main__":
    main()
