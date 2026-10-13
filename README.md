# CloudVault

**AI-Native, Multi-Tenant Cloud File Storage & Collaboration SaaS**

CloudVault bridges the gap between simple object storage and intelligent document management, providing teams with powerful search, summarization, and collaboration capabilities out-of-the-box.

## Key Features (Planned)
- 📂 Secure file and folder management
- 🤝 Granular sharing and access control
- 🤖 AI-powered document summarization
- 🔍 Semantic (RAG) search across your files
- 🏢 Strict multi-tenant data isolation

## Tech Stack
- **Frontend**: React, TypeScript, Vite, Tailwind CSS
- **Backend**: Python, FastAPI, SQLAlchemy
- **Data & Infra**: PostgreSQL, Redis, MinIO/S3, Docker

## Quick Start (Local Development)

1. Clone the repository
2. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
3. Start the infrastructure for running the backend and frontend directly:
   ```bash
   docker compose up -d postgres redis minio minio-setup mailpit
   ```
4. Backend:
   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements-dev.txt
   cp ../.env .env
   alembic upgrade head
   uvicorn app.main:app --reload
   ```
5. Frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

Alternatively, run the complete container stack with `docker compose up --build -d`
and open http://localhost:3000. The backend applies Alembic migrations before starting;
the frontend forwards `/api/v1` requests to the backend through Nginx.
The Compose stack uses development credentials and is not a production deployment.
MinIO and its setup client build from pinned official source revisions because
the public upstream images are unavailable. The first build takes longer; see
[storage build details](infra/minio/README.md). Verify the running stack with
`python scripts/docker_smoke.py`, including an actual object upload/read/delete.

For a directly installed backend, start the email dispatcher in a second backend
terminal with `python -m app.jobs.deliver_email`. Development email is delivered to
the Mailpit inbox at http://localhost:8025 (SMTP port 1025). The full Compose stack
includes the dispatcher automatically. Queued email is not the same as delivered email.

## Verification

- Backend: `cd backend`, then `python -m pytest tests/ -v` and `ruff check .`.
- Frontend: `cd frontend`, then `npm test`, `npm run lint`, and `npm run build`.
- Browser account tests: install Chromium with `npx playwright install chromium`,
  then run `npm run test:e2e` from frontend. Install backend development requirements
  first. The harness uses a disposable migrated SQLite database, real loopback SMTP,
  and isolated local ports 43000/48000/41025/48025; it does not use the application database.
- Local backend tests use a temporary SQLite file. For PostgreSQL tests, set
  `TEST_DATABASE_URL` to a **dedicated disposable database**: fixtures create and
  remove CloudVault tables. Never point this variable at an application database.
- GitHub Actions runs PostgreSQL-backed tests, migration upgrade/check/downgrade,
  and a Docker smoke test covering the frontend, API proxy, and registration.
- Production requires a custom `SECRET_KEY` of at least 32 bytes, generated with
  a cryptographically secure random generator; default development keys are rejected.

## Documentation
- [Architecture Details](ARCHITECTURE.md)
- [Development Plan](DEVELOPMENT_PLAN.md)
- [Agent Instructions](AGENTS.md)
- [Phase Reports](docs/phases/README.md)
- [Phase 2 Explanation](docs/phases/phase2.md)
- [Phase 2A Explanation](docs/phases/phase2a.md)

## Profiles and Organizations

After registering or signing in, open **Profile and organization** from the workspace.
Everyone can edit their name and view their organization's members. Owners and admins
can rename the organization and create invitations. Owners can assign admin roles;
admins can invite and remove ordinary members.

Create an invitation for someone new to CloudVault. It is queued for email delivery;
the private link is also available for secure manual sharing. It expires after seven
days; its recipient chooses their own name/password and separately verifies their
email before using organization features. Pending invitations can be revoked.
Accounts currently belong to one organization; existing accounts cannot be moved or
joined to additional organizations. Removed accounts are disabled.

Run `alembic upgrade head` when upgrading a local backend. Migration `002_memberships`
preserves existing users and backfills memberships for active accounts. Compose applies
migrations automatically on backend startup.

## Account Verification and Recovery

Registration creates an unverified account and queues a verification email. Open its
private link and confirm verification. Existing accounts are also unverified after
the `003_accounts` migration: this migration revokes old refresh cookies and requires
sign-in with the new session format. Existing profile/password data is preserved.

Open **Account security and email** to resend verification, view delivery status,
change email, revoke an individual session, or sign out all devices. Email changes
require the current password and verification at the new address; confirmation revokes
all sessions. **Forgot password?** provides a generic recovery response and a one-use
email link. Password reset revokes all sessions and requires normal sign-in.

Verified non-owner users may delete their account with their password and explicit
`DELETE` confirmation. Profile identifiers are redacted and access is revoked. Owners
are protected until ownership transfer is implemented in Phase 2B. See the phase report
for the retention policy and remaining multi-organization limitations.

Production requires a secure signing key, HTTPS `FRONTEND_URL`, SMTP STARTTLS,
appropriate `SMTP_HOST`/`SMTP_PORT`, and provider-specific username/password/from-address
configuration. Local SMTP success does not verify production delivery. Queued payloads
are encrypted with a key derived from `SECRET_KEY`; rotating that key makes old pending
payloads unreadable, so coordinate worker/backend configuration and resend affected links.

## License
MIT License - Copyright (c) 2026 CloudVault Contributors
