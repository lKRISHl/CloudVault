# CloudVault Architecture

## Overview
CloudVault uses a modular monolith. Global accounts use organization memberships and explicit session workspace selection; Phase 3 adds folder hierarchy; Phase 4 adds pending file metadata; Phase 5 supplies the S3 adapter and Phase 6 connects verified direct uploads.

```text
[Frontend Client (React/Vite)] 
       | (REST API via HTTP)
       v
[Backend API (FastAPI)] 
  |--> [PostgreSQL (Relational Data)]
  |--> [Redis (Caching/Queues)]
  |--> [MinIO (Object Storage)]
```

## Component Descriptions
- **Frontend**: A React Single Page Application built with Vite and Tailwind CSS. It communicates with the backend via REST.
- **Backend**: A Python FastAPI application providing core business logic and API endpoints. 
- **Database**: PostgreSQL handles relational data, configured with async SQLAlchemy and Alembic for migrations.
- **Cache/Queue**: Redis is provisioned for future caching and asynchronous task queues.
- **Storage**: MinIO provides an S3-compatible local object storage environment for file blobs.

## Authentication (Phase 1)
- Register creates a global user, tenant and owner membership.
- Login returns a short-lived JWT access token and sets an HttpOnly refresh cookie.
- Protected routes require an active global user and live session matching the claimed tenant. Workspace routes also require an active membership; current membership roles govern management privileges. Account routes remain usable without an active workspace. JWT role claims do not grant privileges.

## Organizations and Membership (Phase 2)

- The existing `Tenant` is the organization/workspace; there is no duplicate organization table.
- Registration creates a tenant, owner user, membership, and session in one transaction.
- `memberships` records independent roles for each (tenant, global user), with foreign keys to both identities and a revocation tombstone. A partial unique index permits one active owner per tenant. Users store no tenant/role columns; response compatibility properties are populated from the authenticated session's membership.
- `invitations` contains a hashed, seven-day token, bound email and role, issuing user, organization, expiry, consumption timestamp and reactivation flag. Creation/acceptance recheck issuer authority in that organization. Existing verified users must explicitly accept while authenticated with the addressed email.
- Only owners can assign admin roles. Admins can rename organizations, invite members, and remove members; members can edit their own profile and read their organization's roster.
- Ordinary role/removal operations cannot alter the owner. Ownership transfer requires the owner's current password, explicit confirmation and a verified active target member; demotion and promotion commit atomically. Removal marks only that membership revoked and revokes its workspace sessions/refresh tokens and affected invitations. Other organization access and global identity remain available.
- PostgreSQL organization-row locks serialize management operations. Invitation acceptance uses an additional conditional update and commits token consumption, account, membership, and session together.
- Global deletion locks relevant tenants in stable order before the identity, checks ownership across all memberships, and removes all memberships/recovery access only after ownership is transferred. Profile redaction and session revocation remain global operations.
- Frontend routes `/app/settings` and `/join` provide management and invitation onboarding. Query caches are scoped to tenant/user and cleared when authentication changes. Invitation secrets are placed in the URL fragment and cleared after acceptance.
- Workspace listing/creation/switching is available on `/app`. Switching revokes the current session, issues a replacement bound to the selected membership and preserves the absolute expiry; other browser sessions retain their selected workspace. Login selects the earliest active membership deterministically, or an account-only session if none remain. Frontend changes cancel/clear queries and reject stale responses; a shared cookie cannot silently retry an old workspace mutation in a new workspace.
- Migration `004_workspaces` preserves existing accounts, passwords, memberships and valid sessions. Former removal disables become revoked membership tombstones with account-only recovery; identities disabled with intact memberships remain disabled. Downgrade refuses multi-workspace/workspace-less data or incompatible invitation history instead of deleting it.
- Phase 3 supplies a shared-workspace folder permission foundation; Phase 4 supplies pending file metadata; granular ACLs and object lifecycle arrive later.

## Account Lifecycle (Phase 2A)

- JWT access tokens now contain `sid`, referencing a stable `login_sessions` row. Refresh rotation preserves the session ID and seven-day absolute session deadline. Protected requests check membership plus active session state; revocation takes effect on subsequent requests.
- `users.email_verified` defaults to false, including migrated accounts. Organization features require verified email. `account_tokens` stores hashed purpose-bound verification/reset/email-change challenges.
- Registration and invitation acceptance queue a separate verification challenge in their database transaction. Resets and email changes revoke sessions and invalidate account links; confirmation requires new-address verification and current-account reauthentication.
- `email_outbox` stores encrypted mail payloads, attempts, delivery deadlines, leases, and status. A small dedicated SMTP dispatcher processes it separately from requests; general Redis/Celery processing remains Phase 16 work.
- Compose adds a local Mailpit inbox and an email dispatcher. Shared database rate counters protect account endpoints across backend processes without relying on local memory.
- Migration `003_accounts` preserves identities/passwords, marks addresses unverified, and revokes legacy refresh cookies. Legacy access tokens lack the required session claim and are rejected; existing users must sign in and verify their address.
- `/account/recover`, `/account/action`, and `/app/security` provide recovery, verification/email confirmation, delivery status, and session management. Action secrets use URL fragments; successful actions clear those fragments.
- Verified deletion redacts profile identifiers, removes all memberships/recovery tokens, and revokes all access while retaining reference-safe identity tombstones. Ownership in every organization must first be transferred through Phase 2B's ownership flow.

## Folder Hierarchy (Phase 3)

- `folders` stores metadata only: stable UUID, tenant, nullable parent, creator, normalized display/name key and timestamps. A composite parent/tenant foreign key prevents cross-tenant edges; root/child uniqueness enforces names per parent and a check prevents direct self-parent links.
- Adjacency-list hierarchy keeps ordinary moves to one parent update while preserving descendants' IDs. Ancestor traversal checks cycles and builds breadcrumbs; a bounded recursive CTE computes subtree height before moves. Depth is limited to 64.
- All folder reads/writes require verified active membership. Members read shared folders and create at root. Folder creators and organization owners/admins modify folders; parent writes require the same authority. `can_write` is informational UI state; server policy rechecks every mutation.
- PostgreSQL tenant-row locks serialize structural writes per organization. SQLite test/development requests acquire its writer lock with BEGIN IMMEDIATE before reading the mutable graph. Name indexes and cycle/depth checks remain authoritative in both environments.
- Creator account deletion preserves organization-owned folder metadata with its pseudonymous identity reference; active organization managers can maintain it. Deletion/trash and granular permissions belong to Phases 13 and 12 respectively.
- `/api/v1/folders` lists children/breadcrumbs with bounded pagination and creates folders; UUID routes read/rename/move. `/app/folders` provides browsing and destination selection. Queries are scoped by tenant/user/parent/page; missing/forbidden resources do not undergo automatic retries.
- Migration `005_folders` adds the table without changing identities/memberships; downgrade refuses nonempty folders. Seeded preservation and populated downgrade protection are verified on PostgreSQL and SQLite.

## File Metadata (Phase 4)

- `files` contains stable UUIDs, tenant, nullable folder (virtual root), creator provenance, normalized name/key, declared size/type, pending state and timestamps. Organization ownership is independent of creator identity. No file bytes enter PostgreSQL.
- Composite folder/tenant foreign keys prevent cross-tenant placement. File names are unique within their folder/root, with separate file/folder namespaces. Listing index covers tenant/folder/name/id; a creator index supports tenant-scoped provenance queries.
- FileService uses the existing FolderService membership and parent-authority checks. Internal reservations serialize with the same tenant lock as folder writes and organization management; creator and tenant derive from authenticated context. No public creation endpoint exists before upload validation.
- All verified active workspace members can read metadata. Creator or owner/admin authority is reported for future mutations; membership is authoritative. Folder moves preserve file references, and account deletion preserves organization content with a pseudonymous creator.
- Declared size/type do not establish actual size, safe MIME, scan state or availability. Database state currently permits only pending; Phase 6 must add verified object lifecycle transitions and atomic upload/session integration. Later phases add verified transfer/cleanup and resource ACLs; quota policy and versions remain upcoming.
- GET `/api/v1/files` returns a folder/root page (25 default, max 100); GET `/api/v1/files/{id}` returns metadata. The folder browser shows pending metadata with separate pagination and scoped query keys.
- Migration `006_files` preserves accounts/folders and refuses populated downgrade. Empty downgrade/re-upgrade, seeded preservation and schema alignment pass on SQLite/PostgreSQL.

## Object Storage (Phase 5)

- ObjectStorage defines an internal async contract; S3ObjectStorage implements it with Boto3 Signature V4 and executor threads, bounded SDK connection/read timeouts and at most two attempts.
- ObjectRef uses tenant/file/object UUIDs only. Every object operation checks the adapter's tenant scope before network access. Authorized services remain responsible for membership/resource checks; prefixes are not an IAM substitute.
- Small writes/reads are limited to 1 MiB. Conditional create prevents overwrites; HEAD returns actual object metadata, bounded ranged reads use the observed ETag and reject truncated content. Streams close on success/failure; GET/consume/close stay on one worker even if the awaiting task is cancelled.
- Missing objects and conditional conflicts have safe error types; other SDK/transport errors fail closed without raw provider details. Absent deletes are idempotent in the local unversioned deployment.
- Compose creates the local bucket and disables anonymous access before backend startup. Complete S3 settings, redacted credentials, HTTP(S)-origin validation and production HTTPS/default-credential checks are included. AWS can use native credential discovery; custom endpoints require explicit credentials.
- Operator smoke and real disposable-bucket tests check actual object operations, privacy and failure cases. Database readiness is unchanged; no automatic storage probe or public transfer endpoint exists yet. Upload references/lifecycle and presigned URLs arrive with Phases 6/7; no Phase 5 migration is needed.

## Basic Upload Lifecycle (Phase 6)

- File rows now persist object/bucket/request identities, grant expiry and expected checksum. Uploaded state requires verified size/checksum/type/ETag and completion timestamp; legacy pending metadata remains unchanged. Migration 007_uploads refuses populated upload downgrade.
- UploadService reserves metadata and signs in one database transaction, reusing tenant serialization and current parent/membership checks. Request UUIDs are scoped to creator/tenant and reject different declarations. Signing failure rolls back.
- Direct browser PUT signs byte count, SHA-256, application/octet-stream and If-None-Match. The provider validates bytes and denies overwrite. API completion uses checksum-enabled HEAD and fails closed for missing/mismatched/unavailable objects. Completion/reticketing is creator-only and rechecks current parent authority; completion is idempotent.
- Internal/public storage endpoints separate container inspection from browser signing; URLs are signed for their final public host. Local CORS permits exact configured app/test origins while anonymous bucket access stays disabled. Signing responses are no-store and URLs are not persisted.
- Browser hashing/transferring/verifying stages send no app credentials to storage, preserve retry identity and guard session generation. Unmount aborts transfer; ambiguous acknowledgement is reconciled through completion. Uploaded UI is explicitly unscanned.
- Default basic cap is 100 MiB, grant 15 minutes and completion grace 5 minutes. Shared persistent account/IP rate counters protect grant/completion categories. Aggregate quotas, multipart/resume/cleanup, scanning and downloads follow later phases. Issued storage capabilities last until expiry after app revocation, but unauthorized completion is denied.

## Configuration Management
Configuration is managed using `pydantic-settings` on the backend, reading from environment variables. The `.env` file serves as the source of truth for the local development environment.

## Database Setup
- **ORM**: Async SQLAlchemy for performant database interactions.
- **Migrations**: Alembic is configured to manage schema evolutions.

## Future Architecture Vision
As the application scales, the modular monolith may be split into specific microservices (e.g., separating AI processing pipelines). We will introduce Celery for background workers and pgvector for semantic search.

## Core Principles
- **Stateless Backend**: API servers maintain no local state.
- **Modular Monolith**: Code is organized into cohesive modules before premature extraction.
- **Separation of Concerns**: Clear boundaries between routing, business logic (services), and data access.

## Phase 7 download delivery

DownloadService owns permission and integrity decisions; the file router returns a no-store DownloadTicket. The tenant-scoped S3 adapter signs response header overrides for attachment GETs using the public endpoint. The SPA checks session generation/abort before handing off to the native browser download manager. Object bytes do not pass through FastAPI/PostgreSQL or a buffered frontend fetch. No database schema change is introduced; issuance is not recorded as successful delivery. Phase 12 now applies private resource ACLs; version-specific reads remain a future boundary.

## Phase 8 multipart transfers

MultipartService owns initiation, part grants, provider confirmation, completion and cancellation. Files persist the private provider upload ID, fixed chunk size/count, request identity, deadline and transfer state; upload_parts stores declared size/SHA-256 and provider-confirmed ETag/time. Parts are accessed only through an authorized tenant-scoped file. No file bytes enter the API or database. Migration 008_multipart preserves basic uploads and prevents rollback that would discard multipart state.

The browser hashes bounded slices sequentially and retains only the checksum manifest, then sends Blob slices directly through signed UploadPart URLs. Grants bind size and SHA-256. ListParts receipts are independently checked before conditional CompleteMultipartUpload; HEAD must match final length, generic type and the composite SHA-256 before the database records uploaded state. Composite SHA-256 hashes the concatenated binary part digests and is stored with explicit checksum_kind/count; it is distinct from a whole-file SHA-256. Downloads reconstruct the provider's digest-count representation.

Tenant write serialization protects control operations against concurrent permission/hierarchy changes. Provider and database transactions cannot commit atomically: known failed initializations attempt abort, and completion retries inspect an existing object to reconcile lost acknowledgement. Unknown initialization acknowledgements, abandoned sessions and in-flight abort cleanup require Phase 9 lifecycle work. Current-form retries can skip confirmed receipts; browser-reload resume UX is not present.

## Phase 9 resume and upload maintenance

Progress/resume are creator-authorized MultipartService operations, reached from pending file rows. Progress reconciles ListParts and exposes confirmed bytes/declarations; resume compares the original manifest and signs only missing parts. Browser reload discards URLs/file handles; users reselect the original file. The server's original chunk size/deadline are reused. Upload state persists in File/UploadPart; no browser storage contains capabilities or file bytes.

UploadIntent commits the exact provider key/fingerprint/deadline before multipart creation, independently of the file transaction. Failed or lost provider acknowledgements retain that intent. upload-cleanup runs every 60 seconds by default, checking up to 50 eligible File records and 50 intents per tick, rotating by last attempt. It waits until expiry plus grace plus settling delay, aborts exact-key multipart IDs, deletes abandoned objects and verifies absence. Hidden File tombstones release names through partial unique indexes while retaining cleanup references for repeated sweeps. Completed files are excluded. Versioned buckets fail closed until explicit version-aware deletion is implemented.

The supplementary orphan scan uses one provider page per tick and canonical UUID-key validation; production requires an exclusive CloudVault namespace and reviewed maintenance IAM. Its cursor is in worker memory. MinIO's broad-prefix listing can miss uploads and its empty-prefix cache can reset on restart, so current initialization cleanup relies on durable exact-key intents. Local MinIO also has explicit 24-hour stale-upload expiry/hourly scanning. Provider lifecycle guarantees, full-day expiry timing and production S3/R2 behavior remain deployment verification gates.

## Phase 10 filename search

FileSearchService builds one tenant-scoped live-file query with optional normalized literal substring, direct folder/root scope, declaration/status/method/creator filters and whitelisted sorting. Folder names are joined through matching tenant identity. Every order has an ID tie-breaker; bounded offset/limit+1 pagination avoids a separate full count. The API returns public metadata/no-store and delegates all business decisions to the service. It checks current verified membership and a separate persistent search budget.

010_file_search adds partial live-file tenant B-tree indexes and a PostgreSQL pg_trgm GIN index. SQLite omits the GIN explicitly; migration/schema checks still compare other indexes. Downgrade removes search indexes only and preserves file data/shared extension. PostgreSQL needs permission to install the extension or prior operator provisioning. Short/common terms and broad filters can still scan; actual workload tuning and snapshot/keyset pagination remain scalability considerations.

The search page scopes query cache to current workspace/user/filter/page, aborts obsolete requests and resets on workspace/folder changes. It exposes declaration filters, stable sorting, paging, direct folder links and existing member-authorized downloads. It does not inspect file content or claim MIME/malware safety. Phase 12 now enforces effective resource read predicates before pagination and folder context.

## Sharing (Phase 11)
ShareService manages tenant/file-scoped capabilities for completed files. ShareLink stores a 256-bit token SHA-256 hash, optional Argon2 password hash, expiry/revocation, download permission and committed grant count. Public requests resolve the tenant from the capability, require current verified publisher authority and create a tenant-scoped storage adapter only after validation. Common DownloadService object verification covers basic/composite uploads; no object bytes pass through PostgreSQL or the API.

Grants and mutations hold the PostgreSQL tenant lock (SQLite public writer lock) through bounded provider inspection/signing and counter commit. Publisher lifecycle changes revoke affected links in the same transaction. Public metadata is minimal; no membership/folder/provider identity is returned. Storage URLs last at most normal download TTL/remaining share deadline, with provider clock/signing resolution. Revocation prevents new grants; issued URLs and received bytes remain usable. See docs/phases/phase11.md and ADR-028. Resource ACLs are now implemented in Phase 12.

## Resource Permissions (Phase 12)
File/Folder workspace/private visibility and membership-bound ResourceGrant viewer/editor rows feed PermissionService. Local read is workspace visibility, creator/manager authority or an explicit grant; every ancestor must also be readable. A bounded recursive SQL CTE computes readable folder paths. Public search/file/folder lists include effective read predicates before offset/limit and folder context. Editor tags load per page; resource write and management are separate decisions.

Viewers read/download. Editors rename completed files/folders and create content within an editable folder; they cannot manage ACLs, move folders or publish links. Grants do not inherit editing. Creator/manager control still requires readable ancestors; trusted workspace owners/admins can manage private content. Tenant-serialized permission writes revoke file/subtree external links. Member removal deletes explicit grants, and account deletion cascades through memberships. Downloads recheck ACLs during provider work; upload controls retain creator-only session checks plus current resource/parent authorization. Public shares recheck effective publisher access. See ADR-029/docs/phases/phase12.md; no ACL workload benchmark is claimed.

## Trash and Restore (Phase 13)
TrashEntry identifies a tenant/root removal batch with 30-day retention, earliest cleanup, irreversible purge, restore and completion markers. File/Folder trash_id removes resources from live ACL predicates and name uniqueness. Folder operations mark only active descendants; original-location restore clears its batch atomically, preserves ACLs/object identities and never revives older independent trash. Name conflicts roll back. Current creator/manager plus ancestor authority protects trash pages before pagination; mixed-creator subtrees require managers.

Permanent deletion queues intent before provider operations, and a parent purge queues nested independent trash. TrashCleanupService reacquires tenant serialization, waits beyond upload expiry/grace/settle, aborts exact-key multipart remnants, deletes and checks absence on an unversioned configured bucket. Failed/confirmed references are retained and revisited. Restored batches are excluded. Existing Compose upload-cleanup ticks invoke bounded trash maintenance (10 batches, 10 file references each); cleanup_trash also supports --once. Pending transfers keep the Phase 9 lifecycle and block containing-folder trash until finished/cleaned. Phase 14 extends this to every retained application version; provider bucket versioning remains disabled. See ADR-030/docs/phases/phase13.md.

## File Versioning (Phase 14)
FileVersion retains immutable content snapshots with exact object identity/deadline and cleanup markers. File.current_version and monotonically increasing version_generation select current content; verified metadata remains on File for existing consumers. VersionService applies live file/ancestor ACLs, editor/parent write checks, tenant serialization and optimistic generation checks. Initial basic/multipart completions record version 1 atomically; 014_versions backfills existing completed objects. New version uploads use basic conditional PUTs (default 100 MiB cap). Restoring reuses a verified immutable snapshot and records an actor/generation event; logical identity/ACL/name/location stay current. Content changes revoke external links.

Reader history/downloads use current authority and verify the selected basic/composite object. Retained bytes count each snapshot once; pending declarations remain separate. Old multipart intent cleanup recognizes historical refs. Existing cleanup worker processes expired version candidates and trash waits/deletes all pending/completed version refs in bounded attempts. References remain for retry/late writes. Bucket versioning remains disabled, and Enabled/Suspended buckets fail closed; provider VersionId purge and aggregate quotas are not implemented. See ADR-031/docs/phases/phase14.md.

## Version Transfers and Retention (Phase 14A)
VersionPart persists declarations/receipts against a durable FileVersion candidate before provider multipart creation. VersionMultipartService reuses shared proof/signing primitives with logical-file object keys and generation checks. Bounded browser hashing, scoped secret-free session manifests and server history/progress allow original-file reselection and missing-part resume. Cancellation persists before best-effort abort; fixed deadlines and retained refs protect late-write cleanup.

Creator/manager pruning and keep-last policy queue irreversible deletion without pruning current content. New grants/restore stop immediately; cleanup waits original upload expiry/grace and maximum previous GET lifetime plus settling delay. Current content is checked again, and retained usage falls only after confirmed provider absence. Policy and cleanup sweeps are bounded; trash honors prune deadlines. Migration 015_version_transfers adds policy, cancellation/prune markers and version parts, refusing rollback that loses those states. Aggregate quota/audit retention remain 19/20. See ADR-033 and docs/phases/phase14a.md.
