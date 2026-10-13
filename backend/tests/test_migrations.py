import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4


def test_migrations_upgrade_match_models_and_downgrade(tmp_path):
    """Exercise the real Alembic files independently of metadata.create_all."""
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path / 'migrations.db'}",
    }
    backend = Path(__file__).resolve().parents[1]
    for arguments in (
        ["upgrade", "head"],
        ["check"],
        ["downgrade", "base"],
        ["upgrade", "head"],
    ):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=backend,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_phase_two_migration_backfills_existing_active_users_and_preserves_data(tmp_path):
    database = tmp_path / "existing.db"
    environment = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database}"}
    backend = Path(__file__).resolve().parents[1]

    def migrate(target):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *target],
            cwd=backend,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    migrate(["upgrade", "001_auth"])
    tenant_id = uuid4().hex
    users = [(uuid4().hex, "owner", 1), (uuid4().hex, "admin", 1), (uuid4().hex, "member", 0)]
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO tenants (id, name, slug) VALUES (?, 'Existing', 'existing')",
            (tenant_id,),
        )
        for user_id, role, active in users:
            connection.execute(
                "INSERT INTO users "
                "(id, tenant_id, email, full_name, password_hash, role, is_active) "
                "VALUES (?, ?, ?, 'Existing User', 'existing-hash', ?, ?)",
                (user_id, tenant_id, f"{role}@example.com", role, active),
            )
    migrate(["upgrade", "head"])
    migrate(["check"])
    with sqlite3.connect(database) as connection:
        rows = connection.execute("SELECT tenant_id, user_id, role FROM memberships").fetchall()
        assert set(rows) == {
            (tenant_id, user_id, role) for user_id, role, active in users if active
        }
        assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 3
    migrate(["downgrade", "001_auth"])
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 3
        assert connection.execute("SELECT password_hash FROM users").fetchall() == [
            ("existing-hash",),
            ("existing-hash",),
            ("existing-hash",),
        ]
    migrate(["upgrade", "head"])


def test_account_migration_marks_email_unverified_and_revokes_legacy_refresh(tmp_path):
    database = tmp_path / "legacy_sessions.db"
    environment = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database}"}
    backend = Path(__file__).resolve().parents[1]

    def migrate(*target):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *target],
            cwd=backend,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    migrate("upgrade", "002_memberships")
    tenant_id, user_id, refresh_id = uuid4().hex, uuid4().hex, uuid4().hex
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO tenants (id, name, slug) VALUES (?, 'Existing', 'existing')", (tenant_id,)
        )
        connection.execute(
            "INSERT INTO users "
            "(id, tenant_id, email, full_name, password_hash, role, is_active) "
            "VALUES (?, ?, 'legacy@example.com', 'Existing', 'existing-hash', 'owner', 1)",
            (user_id, tenant_id),
        )
        connection.execute(
            "INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at) "
            "VALUES (?, ?, ?, '2030-01-01 00:00:00')",
            (refresh_id, user_id, "a" * 64),
        )
    migrate("upgrade", "head")
    migrate("check")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT email_verified, password_hash FROM users").fetchone() == (
            0,
            "existing-hash",
        )
        revoked, sid = connection.execute(
            "SELECT revoked_at, session_id FROM refresh_tokens"
        ).fetchone()
        assert revoked is not None and sid is None
