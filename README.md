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
- [Phase 2B Explanation](docs/phases/phase2b.md)
- [Phase 3 Explanation](docs/phases/phase3.md)
- [Phase 4 Explanation](docs/phases/phase4.md)
- [Phase 5 Explanation](docs/phases/phase5.md)
- [Phase 6 Explanation](docs/phases/phase6.md)

## Profiles and Organizations

After registering or signing in, open **Profile and organization** from the workspace.
Everyone can edit their name and view their organization's members. Owners and admins
can rename the organization and create invitations. Owners can assign admin roles;
admins can invite and remove ordinary members.

Create an invitation for a new or existing CloudVault account. It is queued for email delivery;
the private link is also available for secure manual sharing. It expires after seven
days. New users choose their name/password and separately verify email. Existing users
sign in with the verified invited address and explicitly accept; their other memberships
stay available. Pending invitations can be revoked. Removed membership access can
only be restored through a new owner-created invitation and verified acceptance.

Use **Your workspaces** on the home page to create or switch workspaces. Roles belong
to each organization. Switching replaces this session and clears cached workspace data;
other browser sessions keep their workspace. Removing a member revokes only that
organization's access. If their current workspace was removed, sign in again to select
another membership or use the account without a workspace.

Owners can transfer ownership from **Profile and organization** to another verified,
active member, using their current password and typing `TRANSFER`. The previous owner
becomes an admin. Ordinary role changes and removals cannot remove the final owner.

Run `alembic upgrade head` when upgrading a local backend. Migration `002_memberships`
preserves existing users and backfills memberships for active accounts. Compose applies
migrations automatically on backend startup.
Migration `004_workspaces` preserves accounts/passwords and valid session selections.
Back up the database before upgrading. Downgrade refuses data that cannot safely fit
the earlier single-workspace model. The local development upgrade backup is ignored
under `.local/backups/`; keep backups outside Git.

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

Verified users may delete their account with their password and explicit
`DELETE` confirmation. Profile identifiers are redacted and access is revoked. Owners
must transfer ownership in every organization first. Deletion removes all memberships
and revokes all sessions. See the phase report for retention and operational limits.

Production requires a secure signing key, HTTPS `FRONTEND_URL`, SMTP STARTTLS,
appropriate `SMTP_HOST`/`SMTP_PORT`, and provider-specific username/password/from-address
configuration. Local SMTP success does not verify production delivery. Queued payloads
are encrypted with a key derived from `SECRET_KEY`; rotating that key makes old pending
payloads unreadable, so coordinate worker/backend configuration and resend affected links.

## Folder Browser

Open **Browse folders** from the workspace, or `/app/folders`. Create folders at
root or within a writable folder, open them to browse children, use breadcrumbs,
rename folders, and move them with the destination browser.

All verified active workspace members can read these shared folders. Creators,
owners and admins can rename/move a folder; creating a child or moving into another
folder also requires permission on that parent. Granular private/shared ACLs arrive
in Phase 12. Folder deletion/trash arrives in Phase 13.

Names are trimmed, Unicode-normalized and case-insensitively unique among siblings;
path separators, control characters and dot-only names are rejected. The tree has
a maximum depth of 64; self/descendant moves and duplicate destination names fail
without changing the hierarchy. File metadata, basic uploads and downloads are implemented.

Migration `005_folders` preserves current accounts and memberships. Back up before
upgrading; downgrade refuses to discard a populated folder table. The running Docker
app is migrated. Local pre-upgrade backups are ignored under `.local/backups/`.

## File Metadata

The folder browser includes a paginated **Files** section with pending and uploaded
metadata. Organization/folder/creator references and normalized names remain tenant
scoped. Uploaded records have verified storage size/checksum and completion time;
declared MIME remains untrusted. No file bytes are stored in PostgreSQL.

Migration `007_uploads` preserves legacy pending metadata and refuses downgrade when
upload references would be lost. Back up before `alembic upgrade head`; restore a
pre-upgrade backup if rollback cannot represent populated data safely. Docker is
rebuilt and migrated; local backups stay ignored under `.local/backups/`.

## Object Storage

Phase 5 adds a tenant-scoped S3 adapter for internal bucket checks, small object
writes/reads, metadata inspection and deletion. UUID keys exclude filenames; small
helpers are limited to 1 MiB. Phase 6 adds presigned uploads, Phase 7 downloads, and Phase 8 multipart transfers.
Compose provisions the local bucket privately and provides all S3 settings.

After `docker compose up --build -d`, run `python scripts/docker_smoke.py` to verify
HTTP services, anonymous listing denial and real objects through mc and the backend
adapter. Phase 5 needed no migration; Phase 6 advances the app to `007_uploads`.

Direct installations need backend requirements and complete S3 settings from
`.env.example`. TLS follows S3_ENDPOINT; configure addressing style and bounded SDK
timeouts. Real contract tests create unique disposable buckets when TEST_S3_ENDPOINT,
TEST_S3_ACCESS_KEY and TEST_S3_SECRET_KEY are set. Run from backend with
`python -m pytest tests/test_storage_integration.py -q`; no application bucket is cleared.
See the phase report for production/provider limits and operational details.

## Basic Uploads

Verified members can upload at root or inside a writable folder at `/app/folders`.
Select a file and click **Upload file**. The browser hashes it and sends bytes directly
to private storage; the API verifies actual object size/checksum before displaying
**Uploaded**. The basic cap is 100 MiB. Uploads remain unscanned; completed files support downloads.

For retry within the authorization window, the creator chooses the same file from
its pending row. Conditional writes prevent overwrites and completion reconciles lost
acknowledgements. Grant lifetime is 15 minutes with a 5-minute completion grace.
Expired pending names and abandoned objects await Phase 9 cleanup. Multipart transfers
are implemented in Phase 8; reload resume remains Phase 9. Rate limits apply to grants/completions.

Configure API-reachable S3_ENDPOINT and browser-reachable S3_PUBLIC_ENDPOINT for the
same storage bucket, with exact-origin CORS and the signed PUT headers. Compose already
provides these for localhost. Production uses HTTPS and needs provider compatibility/
IAM verification. Existing presigned capabilities last until expiry; completion still
checks current workspace/creator/parent authority.

`python scripts/upload_smoke.py` exercises actual Docker registration, Mailpit
verification, direct transfer and verified metadata. It retains a unique development
account/workspace/file. Real browser tests need TEST_S3_ENDPOINT, TEST_S3_ACCESS_KEY and
TEST_S3_SECRET_KEY; the harness creates a disposable bucket/database and explicitly
cleans its bucket, including on Windows. See the phase report for cleanup recovery.

## License
MIT License - Copyright (c) 2026 CloudVault Contributors

## Downloading files (Phase 7)

In Files & folders, Download is available on uploaded files for verified members of the selected workspace. CloudVault checks the stored object and issues a five-minute attachment link; the browser downloads directly from private storage. Files remain unscanned. Downloads do not require write permission; private resource ACLs are a later phase.

Set DOWNLOAD_URL_SECONDS (30–900, default 300) in the development environment if needed, then rebuild/start Compose. No Phase 7 migration is required. Issued links can be reused until expiry and survive logout/removal until then; browser/provider errors after handoff require a new download attempt. See docs/phases/phase7.md for verification and limitations.

## Multipart uploads (Phase 8)

Choose **Use multipart upload** for smaller files, or select a file above the basic cap
to use chunks automatically. Defaults are 1 GiB maximum, 8 MiB parts and a one-hour
deadline. Configure MULTIPART_MAX_BYTES, MULTIPART_PART_BYTES and
MULTIPART_UPLOAD_SECONDS in `.env`; Compose forwards them. Empty files use basic upload.
The browser hashes bounded slices and transfers them directly; CloudVault verifies
provider part receipts and the assembled object before showing Uploaded. Multipart
checksum metadata is explicitly a composite digest, distinct from a whole-file hash.

Failed parts get up to three attempts. Retry the same selected file while authorization
is valid to skip confirmed parts. **Cancel multipart transfer** or the pending file's
cancel control requests provider abort; cancelled names remain reserved until cleanup.
Browser-reload resume and automatic abandoned-upload cleanup are Phase 9.

Back up existing data before `alembic upgrade head` (008_multipart). Docker performs
the migration on backend startup. Downgrade refuses to discard multipart records;
restore a pre-upgrade backup when rollback cannot represent them safely. Local backup
`.local/backups/cloudvault-before-phase8.sql` is ignored. Tests use disposable data only.

After rebuild, `python scripts/upload_smoke.py` checks real SMTP, basic and multipart
uploads, exact downloaded bytes and metadata. It keeps one unique development account,
workspace and two files. Real multipart provider tests are
`python -m pytest tests/test_multipart_integration.py -q` from backend with TEST_S3
settings. Browser checks are `npm run test:e2e` with those settings from frontend.
