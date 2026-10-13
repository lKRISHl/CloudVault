import os
import subprocess
import sys
from pathlib import Path


def test_migrations_upgrade_match_models_and_downgrade(tmp_path):
    """Exercise the real Alembic files independently of metadata.create_all."""
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path / 'migrations.db'}",
    }
    backend = Path(__file__).resolve().parents[1]
    for arguments in (
        ["upgrade", "head"], ["check"], ["downgrade", "base"], ["upgrade", "head"],
    ):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=backend, env=environment, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
