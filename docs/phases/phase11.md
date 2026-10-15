# Phase 11 — Sharing

Implemented and locally verified on 2026-10-15. Schema: 011_sharing. Final verification is recorded below.
Phase 10 is committed as d4aa3e1; Phase 11 is committed as fa6a27e.

## A. What was built

External share links for completed files, configurable expiry, optional passwords,
metadata-only links, a maximum number of download grants and explicit revocation.
Creators and workspace managers manage links from folder browsing or search. Recipients
use a public page without a CloudVault account. Folder sharing, private resource ACLs
and previews are separate upcoming features.

## B. Why

A collaborator sometimes needs one file without joining the workspace. An expiring
capability grants narrowly scoped access while preserving the private storage bucket
and existing object verification. Password protection is optional additional proof;
the secret link itself must still be handled as a credential.

## C. Architecture

ShareService owns authorization, creation, listing, revocation, public access and grant
accounting. Routes validate typed requests and delegate business logic. ShareLink stores
the tenant, file, publisher, SHA-256 token hash, optional Argon2 password hash, expiry,
revocation and grant restrictions. It never stores a raw token/password or file bytes.

The public service derives tenant scope from the hashed capability rather than a caller
tenant field. File lookup requires both file ID and link tenant. Current active verified
publisher membership and current creator/manager authority are required. Member removal,
role updates, ownership transfer and account deletion permanently revoke affected links
within their existing transactions. Publisher logout alone does not revoke a share.

PostgreSQL grants and mutations acquire the tenant row lock. SQLite uses a writer lock
for public grant handling. Authorization and grant counting are checked under the lock,
which stays held during storage inspection/signing. A concurrent request cannot exceed
the last available grant. This serializes public requests with tenant writes and needs
production throughput/abuse review; no scalability benchmark is claimed.

Only after capability/password/restrictions succeed does the public route create an
adapter scoped to the resolved tenant. DownloadService.checked_url reuses configured
bucket, actual HEAD size/checksum/ETag/type and attachment signing checks for basic and
multipart objects. A failed provider operation does not consume a grant. Successful
signing and the counter commit happen before returning the URL.

## D. Important files

- backend/app/models/share.py and migrations/versions/011_sharing.py.
- backend/app/schemas/shares.py, services/shares.py and api/shares.py.
- backend/app/storage/provider.py and api/storage.py: late scoped adapter factory.
- backend/app/services/downloads.py: common verified object checks.
- backend/app/services/organizations.py and accounts.py: publisher lifecycle revocation.
- backend/tests/api/test_shares.py and tests/test_sharing_migration.py.
- frontend/src/features/sharing/SharingPages.tsx, services/api.ts and types/index.ts.
- frontend/src/features/folders/FileList.tsx and features/search/FileSearchPage.tsx.
- frontend/src/__tests__/Sharing.test.tsx and e2e/sharing.pw.ts.
- scripts/upload_smoke.py, CONTINUE.md and ADR-028.

## E. Technical concepts

A random 256-bit capability is distinct from a predictable resource ID. SHA-256 is
suitable for storing a high-entropy token lookup; human passwords use Argon2. The token
is delivered in a URL fragment, which is excluded from ordinary HTTP request targets.
The SPA takes it into component memory and removes the fragment from its current
address/history. Public API requests send token/password in POST bodies with cookies
and authorization omitted. Application/referrer/cache handling avoids incidental leaks;
TLS and production request-body logging/redaction review remain deployment requirements.

The download limit counts URL grants, not bytes or completed downloads. One signed URL
can be reused until its provider expiry. A lost response after commit still consumes a
grant. There is no exactly-once recipient download or delivery telemetry claim.

## F. Request flow

1. From a completed writable file choose Share. The backend checks current verified
   membership, file tenant, creator/manager authority and folder hierarchy.
2. Choose expiry (1–720 hours, default 24), optional password (8–128 characters), whether
   downloads are allowed and optional maximum grants (1–10000).
3. Save the returned link immediately. Its secret cannot be retrieved from listing;
   losing it requires revoking that entry and creating another. Send passwords separately.
4. A recipient opens the full link and submits any password. Unknown/expired/revoked,
   wrong-password and unavailable-publisher cases return the same unavailable response.
5. Successful access reveals filename, verified byte size, expiry and download availability
   only; no tenant/member/folder/provider references or checksums are disclosed.
6. Download rechecks everything, verifies the actual object, signs an attachment GET and
   commits one grant. Browser navigation streams bytes directly from object storage.
7. Revoke prevents new access/grants. Published storage capabilities already issued remain
   usable until their short expiry; previously received bytes cannot be recalled.

## G. Security

Every management query includes active tenant/file scope. Read-only members cannot create,
list or revoke another creator's links. Pending/cleaned files cannot be shared. The public
adapter accepts only the tenant established by a valid share; clients cannot submit keys,
buckets, tenant IDs or alternate objects. Public response models expose minimal metadata.

Public access/download share persistent budgets of 100 per IP and 100 per hashed capability
per configured window (15 minutes by default), applied before password work. Known and
unknown valid-format tokens consume IP limits. Create/revoke use normal 10 identity/100 IP
category limits. Proxy/IP trust, distributed abuse, password CPU limits and service-level
timeouts need production review. Malformed validation failures do not reach service budgets.

Sharing responses, including validation/denial errors, use no-store/no-referrer. Frontend
public requests never refresh or revoke the signed-in account session. Management cache
keys and remounting include workspace/user/file; late responses cannot repopulate a previous
workspace. Opening another share in the same tab clears previous password/result/request.

Issued URLs use at most the normal download duration (default 5 minutes) and remaining share
deadline, recalculated after HEAD inspection. Provider signing/clock resolution remains a
small timing boundary; revocation never claims immediate invalidation of issued capabilities.
Files remain unscanned and are forced to download as attachments/octet-stream.

## H. Verification

- 225 backend tests pass on SQLite and disposable PostgreSQL with actual MinIO enabled;
  final PostgreSQL sharing/migration recheck passes all 11 cases. Full suite durations:
  SQLite 183.88 seconds, PostgreSQL 195.16 seconds. No production benchmark is claimed.
- Capability/password/minimal metadata, tenant/member/pending access, expiry/revocation,
  provider failure without counting, near-expiry provider work, final-grant concurrency,
  paging/file binding and publisher removal/reactivation/role/account deletion are tested.
- Migration tests check alignment, empty rollback/re-upgrade, populated refusal and
  preserved file/account/link rows on both databases. Existing regression checks pass.
- 66 frontend tests, ESLint, TypeScript/Vite build, Ruff and whitespace checks pass.
  Management denial, restrictions/one-time URL/revoke, credential omission, password
  failures, native navigation, cancellation and same-tab replacement are covered.
- All 16 Chromium/SMTP/storage journeys pass in 55.2 seconds. Sharing validates real
  bytes, signed-out recipient/no account credentials, password protection, grant limits,
  revocation, metadata-only access, second link in the same tab and mobile layout.
- Browser tests found a login-dependent public adapter and stale same-tab token state;
  both were corrected before final checks. Owned browser buckets were cleaned up.
- Rebuilt Docker HTTP/private-bucket/mc/adapter smoke and SMTP/basic/multipart transfer,
  search and anonymous sharing smoke pass. Multipart shared bytes, cap/revoke and basic
  metadata-only access are checked against actual MinIO. Live schema 011_sharing has
  no drift; maintenance succeeds with zero eligible records. All services are running.
- Ignored logs live under .local/phase11-*.log; pre-upgrade backup is preserved. Unique
  development smoke data remains. No push, remote CI, production provider/security/load
  verification or Safari/Firefox certification was performed.

## I. Decisions and tradeoffs

ADR-028 records file-only external capabilities, optional password verification on every
request, minimal metadata, publisher lifecycle revocation and transactional grant limits.
Public share access bypasses account login but never storage tenant scope. Keeping the
tenant lock during bounded provider operations makes revocation/grant ordering explicit,
with a throughput cost. Public sharing is not recipient identity verification or private
viewer/editor access; those controls belong to Phase 12.

## J. Operations and limitations

Run docker compose up --build -d, then python scripts/docker_smoke.py and
python scripts/upload_smoke.py. Share from /app/folders or /app/search. FRONTEND_URL
must point to the intended recipient origin; direct setups back up then run alembic
upgrade head. Ignored pre-upgrade backup: .local/backups/cloudvault-before-phase11.sql.

011_sharing creates metadata only and preserves files/accounts. An empty sharing table
can downgrade to 010; any retained link makes downgrade refuse. Restore the pre-upgrade
backup for unrepresentable rollback, understanding the resulting state difference. There
is no automatic link-record purge or raw-secret recovery; metadata is retained for management.

Only files are shared. Metadata-only links show filename/size, with no preview or bytes.
Links do not grant uploads, editing, folder traversal, workspace membership or AI access.
Links can be forwarded, passwords are optional, and recipient identity is not established.
Per-link/IP budgets may require waiting even for legitimate large recipient groups.
Grant URLs can be reused; ambiguous API acknowledgement consumes a grant. Link creation
is not idempotent; an uncertain creation can be found/revoked by management, then retried.
The public page clears the fragment, so reload requires reopening the original complete link.

Private ACLs (12), trash (13), versions (14), previews (15), scans (17), quotas (19), audit
logs (20), AI (21+), maintained production storage, SMTP, MFA, remote CI, monitoring,
backup/restore, representative load and deployment security gates remain pending.
Local MinIO is archived and for development only. SQL backups do not restore object bytes.

## K. Interview discussion

- Why hash tokens and passwords differently? Tokens have high random entropy; passwords
  require a slow, salted verifier against dictionary attacks.
- Why put the secret in a fragment? It avoids normal HTTP URL/access-log/referrer exposure;
  POST-body and browser-memory handling still need appropriate security controls.
- How do concurrent recipients respect the last grant? Tenant serialization, fresh link
  state and a counter commit before returning the signed URL.
- Why can revocation not recall a download? Storage URLs and downloaded bytes have their
  own lifetimes; application revocation prevents subsequent grants.
- How do private ACLs change sharing? Phase 12 must centralize resource authority for
  publishing and ongoing access without leaking metadata through search or lists.
