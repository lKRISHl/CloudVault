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

Phase 12 now enforces workspace/private visibility and mandatory ancestor read gates.
Explicit viewers can browse; editors can rename/create content within the folder.
Creators/managers control moves and ACLs, and the destination must be writable.
Folder deletion/trash arrives in Phase 13.

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
are implemented in Phase 8; Phase 9 adds reload resume and automatic cleanup. Rate limits apply to grants/completions.

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
Phase 9 now adds browser-reload resume and automatic abandoned-upload cleanup below.

Phase 8 introduced 008_multipart; the current head is 009_upload_cleanup. Back up
existing data before `alembic upgrade head`. Docker performs
the migration on backend startup. Downgrade refuses to discard multipart records;
restore a pre-upgrade backup when rollback cannot represent them safely. Local backup
`.local/backups/cloudvault-before-phase8.sql` is ignored. Tests use disposable data only.

After rebuild, `python scripts/upload_smoke.py` checks real SMTP, basic and multipart
uploads, exact downloaded bytes and metadata. It keeps one unique development account,
workspace and two files. Real multipart provider tests are
`python -m pytest tests/test_multipart_integration.py -q` from backend with TEST_S3
settings. Browser checks are `npm run test:e2e` with those settings from frontend.

## Resuming and cleaning uploads (Phase 9)

After reload or interruption, click **Resume upload** on your pending multipart file.
CloudVault shows server-confirmed progress. Reselect the original file and click
**Upload file**; its original chunk layout is checked, and only missing parts transfer.
The original deadline still applies. If all parts arrived during the completion grace,
**Verify completed upload** can finish without sending bytes. An expired session requires
a fresh upload after cleanup releases its name.

Compose includes upload-cleanup. It checks expired pending transfers every 60 seconds
by default, after completion grace plus a 300-second settling delay. It aborts unfinished
provider uploads, deletes abandoned objects and verifies absence before releasing names.
Hidden references remain for repeated cleanup of late writes. Cancelled names are released
after the original transfer deadline and safety delays, rather than immediately.

For direct setups run `python -m app.jobs.cleanup_uploads` in a backend terminal with
the same database/S3 settings. `--once` runs one maintenance tick. Configure
UPLOAD_CLEANUP_INTERVAL_SECONDS and UPLOAD_CLEANUP_SETTLE_SECONDS as needed. The worker
checks at most 50 File records and 50 initialization intents per tick; larger queues
need multiple ticks. Provider failures preserve references and rotate attempts.

Back up before upgrading to 009_upload_cleanup. The ignored local backup is
`.local/backups/cloudvault-before-phase9.sql`. Downgrade refuses cleanup tombstones or
initialization intents. Database backups cannot restore reclaimed object bytes; storage
backups need a separate provider plan. Destructive tests continue to use disposable data.

Current cleanup requires an unversioned bucket and reviewed maintenance permissions.
MinIO is local-only; exact-key durable intents address its inventory limitations. Compose
also configures local stale-upload expiry at 24 hours/hourly scanning. Production S3/R2
lifecycle, IAM, version-aware cleanup, monitoring and backup/restore remain deployment gates.

## Finding files (Phase 10)

Open **Search files** from navigation, or **Search this folder** while browsing.
Search part of a filename and combine scope/status/transfer method/creator/declared-type/
byte filters. Sort by filename, size, created or updated date; choose 5/25/50 results per
page. Results show folder context and link to normal browsing; completed files retain
authorized downloads. New searches/cleared filters reset pagination.

Search is case-insensitive with Unicode NFC/case folding; accents stay significant.
Percent/underscore match literal characters. Folder scope searches direct children.
Pending size/MIME are declarations, and files remain unscanned. Search currently follows
effective resource ACLs and mandatory ancestor boundaries from Phase 12.

Back up before upgrading to 010_file_search. PostgreSQL needs pg_trgm provisioning
permission (or prior operator installation); SQLite uses the B-tree fallback. Search
index rollback to 009 preserves data and the shared extension. The local ignored backup
is `.local/backups/cloudvault-before-phase10.sql`. Rebuild/start Compose after changes.

API pages cap at 100 and offsets at 10000. Short/common terms can still scan; synthetic
index verification is not a production benchmark. Review query logging, workloads,
database timeouts, maintenance and deployment gates before production.

## Share files (Phase 11)
From Files or Search files choose Share on a completed writable file. Set expiry (1–720 hours; default 24), an optional password, Allow downloads and an optional grant cap. Save the generated URL immediately; its raw secret is not retrievable later. Send any password separately. Existing links are paginated and revocable. Recipients open the original full link at /share, check access and download directly from private storage.

Grant caps count issued URLs, not completed downloads; lost API acknowledgement still consumes a grant. Metadata-only links reveal filename/size without previews. Revocation blocks new access/grants; previously issued URLs work until expiry. Removing/changing publisher membership or deleting their account revokes affected links. Public requests omit CloudVault account credentials. Reloading the recipient page requires reopening the original full link because the address fragment was cleared.

Back up before alembic upgrade head (011_sharing); Docker backend startup migrates. A populated sharing table refuses downgrade: restore a pre-upgrade backup for an unrepresentable rollback. Run docker compose up --build -d, python scripts/docker_smoke.py and python scripts/upload_smoke.py for local verification. Tests use disposable databases/buckets. See docs/phases/phase11.md and CONTINUE.md for evidence and production gates.

## Control resource access (Phase 12)
Choose Permissions on a managed file/folder in Files or Search files. Existing content is workspace-visible. Make it private and select verified workspace members from paginated candidates for Viewer or Editor access. Viewers read/download. Editors rename completed files/folders and add content within editable folders. Creators and managers control permissions, folder moves and external share links.

Every containing folder must be readable. A direct file grant cannot bypass a private ancestor; grant each required private ancestor separately. Editor grants affect their resource and do not inherit editing over other creators' children. Removing a grant does not remove workspace visibility or creator/manager rights. Permission changes revoke external links for the affected file/folder subtree; issued storage URLs remain valid until expiry. Moving a folder changes its ancestor restrictions. Member removal deletes explicit grants.

Back up before alembic upgrade head (012_permissions); Docker startup migrates. Downgrade refuses any private visibility or explicit grant; restore a pre-upgrade backup for an unrepresentable rollback. Run docker compose up --build -d, python scripts/docker_smoke.py and python scripts/upload_smoke.py. The latter verifies private hiding, real viewer download, editor rename and revoked access using a second verified member. See docs/phases/phase12.md and CONTINUE.md for evidence and remaining deployment gates.
