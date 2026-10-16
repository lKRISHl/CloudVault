# Architectural Decision Records

## ADR-001: Modular Monolith Architecture
- **Context**: Starting a new SaaS product with uncertain domain boundaries.
- **Decision**: Adopt a modular monolith architecture.
- **Rationale**: Reduces operational overhead and simplifies deployments while allowing for future microservice extraction if needed.
- **Alternatives considered**: Microservices (rejected due to premature optimization and overhead).

## ADR-002: Async SQLAlchemy with asyncpg
- **Context**: Need high-performance database access for a FastAPI application.
- **Decision**: Use SQLAlchemy with the asyncpg driver.
- **Rationale**: Maximizes concurrency and integrates cleanly with FastAPI's async nature.
- **Alternatives considered**: Synchronous SQLAlchemy, Tortoise ORM.

## ADR-003: Pydantic Settings for Configuration
- **Context**: Managing environment variables and configurations securely.
- **Decision**: Use `pydantic-settings`.
- **Rationale**: Provides strong typing and validation for environment variables out-of-the-box.
- **Alternatives considered**: os.environ, python-decouple.

## ADR-004: S3-Compatible Object Storage
- **Context**: Storing user files and assets securely and scalably.
- **Decision**: Use MinIO for local development and S3/R2 for production.
- **Rationale**: S3 API is the industry standard; MinIO provides an exact local replica.
- **Alternatives considered**: Storing files in DB (rejected due to performance/cost), local filesystem (rejected for scalability).

## ADR-006: JWT Access Tokens + Rotating Refresh Cookies
- **Context**: Phase 1 needs authentication for a browser SPA without placing long-lived secrets in JavaScript storage.
- **Decision**: Issue short-lived JWT access tokens in the JSON body and rotating refresh tokens in HttpOnly `SameSite=lax` cookies. Persist only SHA-256 hashes of refresh tokens.
- **Rationale**: Access tokens stay out of localStorage; refresh tokens can be revoked server-side; rotation invalidates stolen cookies after use.
- **Alternatives considered**: Server sessions in Redis only, JWT in localStorage, opaque access tokens.

## ADR-007: One Tenant Per User at Registration
- **Context**: CloudVault is multi-tenant; registration must create an isolated workspace.
- **Decision**: Registering creates a tenant plus the first user as `owner`. Users currently belong to a single tenant via `users.tenant_id`.
- **Rationale**: Delivers tenant isolation immediately without a membership join table. Organization membership is planned in Phase 2; resource permissions are planned in Phase 12.
- **Alternatives considered**: Global users with a memberships table from day one.

## ADR-005: PostgreSQL + pgvector for Vector Search
- **Context**: Needing vector storage for AI semantic search.
- **Decision**: Use PostgreSQL with the pgvector extension.
- **Rationale**: Keeps relational and vector data in the same datastore, simplifying operations and transactions.
- **Alternatives considered**: Pinecone, Milvus, Qdrant (rejected to reduce infrastructure complexity initially).

## ADR-008: Atomic Refresh Rotation and Shared Browser Refresh
- **Context**: Concurrent requests could read the same valid refresh token and issue multiple replacements.
- **Decision**: Claim refresh tokens using `UPDATE ... WHERE revoked_at IS NULL AND expires_at > now RETURNING id`; commit that update together with replacement insertion. Logout also uses a conditional update. Share one in-flight refresh promise within each frontend tab, including React StrictMode startup.
- **Rationale**: Enforces one successful rotation in shared database state across backend instances, without relying on process-local locks. Local concurrency tests use separate sessions against a temporary SQLite file; CI runs them against PostgreSQL.
- **Limitations**: Separate tabs do not share the frontend promise. Token-family revocation on replay is deferred to security hardening.

## ADR-009: Phase 0–1 Verification and Development Startup
- **Context**: The abbreviated development plan diverged from the master roadmap, and Docker frontend ports and proxy paths were inconsistent.
- **Decision**: Restore the full Phase 0–33 roadmap. Run development migrations before the Compose backend starts; serve frontend port 80 through host port 3000 and preserve `/api/v1` in proxy requests. Add PostgreSQL and Docker smoke verification to CI.
- **Limitations**: Development startup assumes one backend container. Production migration orchestration is deferred to deployment phases. Docker and PostgreSQL are unavailable on the current host, so CI checks remain unverified until run remotely.

## ADR-010: Organizations Reuse Tenants with Explicit Memberships
- **Context**: Phase 1 already creates a workspace on registration and stores each user's tenant and role. Phase 2 requires organization membership without breaking existing accounts or auth responses.
- **Decision**: Treat `Tenant` as the organization. Add `Membership` with a composite user/tenant foreign key, role constraint, and unique user constraint. Backfill active existing users in migration `002_memberships`. Keep `User.role` as a compatibility field synchronized with membership role; authorization reads the database and authentication rejects inconsistent rows.
- **Rationale**: Avoids duplicating workspace identity or moving existing accounts. Basic organization collaboration works within the already documented single-tenant model.
- **Alternatives**: A separate organization table would duplicate tenant identity. Global users with multiple memberships would require a tenant-switching/session redesign beyond this phase.
- **Limitations**: One organization per account; owner transfer and moving/reactivating existing accounts are not implemented.

## ADR-011: Invitations and Serialized Organization Management
- **Context**: Membership needs a real onboarding path that does not let administrators choose another person's password or move their account silently. Concurrent management and invitation acceptance must preserve authorization and transaction invariants.
- **Decision**: Owners/admins create seven-day invitation secrets and share them manually; only the hash is persisted. New users redeem a token and choose their own name/password. Organization-row locks serialize PostgreSQL management mutations; conditional invitation consumption ensures one successful acceptance. Account, membership, invitation consumption, and session commit together. Resending supersedes previous pending tokens for the same organization/email; role changes/removal invalidate the target's issued invitations.
- **Roles**: Owners alone assign/invite admins. Admins invite/remove members and rename the organization. Members edit their own profile and read the roster. Owner membership is immutable.
- **Frontend**: Invitation secrets use URL fragments to avoid inclusion in HTTP request URLs; the fragment is removed on successful join. Queries are scoped by tenant/user, and auth changes clear cached data.
- **Limitations**: No email transport or proof of mailbox ownership. Possession of a private invitation link grants access to the bound email's new account, so links must be shared securely. SQLite concurrency tests cover conditional updates but do not prove PostgreSQL row-lock behavior; CI verification is pending.

## ADR-012: Explicit Roadmap Extensions and Verification Criteria
- **Context**: The owner requested that current account/membership limitations and missing subscription work receive explicit future implementation slots, rather than relying on unspecified later hardening.
- **Decision**: Preserve original Phase 0–33 numbers. Schedule Phase 2A for email/account/session lifecycle, Phase 2B for multi-organization identity/membership lifecycle before file/folder implementation, and Phase 25A for billing after quotas/audit/webhooks. Define completion criteria and keep PostgreSQL/Docker verification as an immediate pending gate.
- **Rationale**: Account verification precedes existing-account onboarding, and the future user/membership model should be settled before file schemas depend on it. Billing depends on reliable entitlements, quotas, and webhook handling.
- **Status**: Planning only. Existing schemas and single-organization behavior are unchanged. New phases require explicit start instructions; no push or remote CI dispatch is authorized by this planning change.

## ADR-013: Verified Account Actions and Live Session Revocation
- **Context**: Phase 2A needs verified-email privileges, recovery, email changes, and immediate session revocation. Phase 1's JWT expiry alone cannot revoke an already-issued access token.
- **Decision**: Add hashed purpose-bound account challenges and stable login-session rows. JWTs reference the session ID; protected requests check live revocation/expiry and membership. Refresh rotation retains the session ID and absolute seven-day deadline. Reset/email confirmation invalidates sessions and outstanding account links. Verification is independent of invitation possession.
- **Migration**: 003_accounts preserves users/passwords, marks legacy addresses unverified, and revokes old refresh cookies. Tokens without a valid session ID are rejected; existing users must sign in and verify email. Do not infer verification from historic registration.
- **Tradeoff**: Database-backed checks add request work but make revocation effective across backend instances without stale process-local caches. Account endpoints use shared atomic database rate counters; recovery has a generic response and minimum response duration, not a formal constant-time guarantee.
- **Deletion**: Verified non-owners can remove profile/access with current password and explicit confirmation; minimal reference-safe tombstones remain. Owner deletion/transfer and full multi-organization handling are deferred to Phase 2B.

## ADR-014: Encrypted SMTP Outbox and Technical Retention
- **Context**: Email transport failures must not block account requests or expose recovery secrets in persisted plaintext or logs.
- **Decision**: Queue encrypted mail payloads in the same transaction as their account actions. Fernet encryption uses a domain-separated key derived from SECRET_KEY. A dedicated SMTP process claims leased messages, uses a stable Message-ID, retries bounded failures, and stops before the mail/link deadline. Sent, superseded, and expired payloads are cleared; statuses contain safe metadata only. General Redis/Celery infrastructure remains Phase 16.
- **Development**: Mailpit provides a local SMTP inbox; backend integration tests and Chromium E2E additionally use a real loopback SMTP receiver. Production requires HTTPS callback configuration and SMTP STARTTLS/provider configuration.
- **Limits**: SMTP acknowledgement can be ambiguous after a crash; delivery is at-least-once, not exactly-once. Single-use tokens prevent repeated account-state changes. Signing-key rotation also changes outbox encryption: coordinate configuration and resend pending links as needed.
- **Retention**: The running mail maintenance job clears expired rate counters and obsolete account tokens/session/refresh/invitation records 30 days after expiry or revocation/consumption as applicable, and mail metadata 30 days after creation. Self-deletion immediately removes account challenges, redacts profile/incoming invitation addresses, and clears pending personal mail payloads. Reference IDs/timestamps remain for integrity; delivered external email cannot be recalled.

## ADR-015: Browser Account Verification and Dependency Security Updates
- **Context**: Component tests with mocked fetch do not verify full mailbox-to-browser account flows. npm audit also reported known vulnerabilities in the prior frontend packages.
- **Decision**: Add Playwright Chromium journeys using a disposable migrated SQLite backend and real local SMTP delivery, with no production test endpoints/database reuse. CI installs browser/Python requirements and runs these journeys. Update affected Vite/Vitest/React Router/TypeScript ESLint packages and compatible build plugins; use Vitest-specific DOM matcher integration.

- **Verification**: Local component/API/migration/SMTP/browser checks and build/lint pass; npm audit reports zero known vulnerabilities at this verification point. That result is not a guarantee against unknown vulnerabilities. Subsequent PostgreSQL/storage verification is recorded in ADR-016 and CONTINUE.md; production-provider verification remains pending.

## ADR-016: Build Development Storage from Pinned Official Sources
- **Context**: MinIO server/client images cannot be pulled from Docker Hub or the checked Quay alternatives. Official community repositories are archived; the server README documents source-only distribution.
- **Decision**: Build development server/client binaries from immutable official repository commits in `infra/minio/Dockerfile`, using Go module checksums, bounded compilation parallelism and minimal Alpine runtime stages. Preserve upstream licenses and existing volume/bucket configuration. No third-party binary mirror is introduced.
- **Verification**: Add `scripts/docker_smoke.py` to check HTTP services and upload/read/delete a unique object in the development bucket; run it in Docker CI too. PostgreSQL verification now passes locally: 81 backend tests and Alembic upgrade/check/downgrade/re-upgrade on a separate database.
- **Limitations**: First source compilation takes longer and requires GitHub/Go module access. Archived upstream software requires a maintained S3 provider/deployment decision before production; this fix restores development startup, not production certification.
- **Sources**: https://github.com/minio/minio and https://github.com/minio/mc.

## ADR-017: Global Identity, Membership Revocation and Workspace Sessions
- **Context**: A tenant/role stored on each user prevents additional organization membership and makes scoped removal disable the whole identity. The file phases must build on the final membership model.
- **Decision**: Remove persisted user tenant/role; retain global account identity. Memberships carry role/revocation with independent tenant/user foreign keys. API compatibility properties are populated per request from authorized membership. A session selects one tenant, checked against the JWT tid; account-only sessions use an empty tid when no memberships remain. Login picks the earliest active membership deterministically.
- **Switching**: Revoke the current session/refresh tokens and issue a new session for the selected membership with the same absolute expiry. Other browser sessions retain their selection. Cancel/clear query caches and reject stale responses. Do not retry an old workspace mutation under a different tenant obtained through shared-cookie refresh; public verification/recovery is independent of workspace changes.
- **Lifecycle**: Existing invitation acceptance requires a verified authenticated identity matching the addressed email. Removal keeps a membership tombstone and revokes only affected workspace sessions/invitations. Reactivation requires a new owner-created invitation, current owner authority, verified acceptance, and an explicit role; old credentials remain revoked.
- **Migration**: Preserve accounts/passwords and bind existing live sessions to their former tenant. Legacy removed identities become account-only identities with revoked membership/session state. Suspensions with intact memberships stay disabled. Downgrade refuses incompatible multi-workspace/workspace-less identities or invitation history; restore a backup rather than silently discard data.

## ADR-018: Atomic Ownership Transfer and Global Account Deletion
- **Decision**: One active owner per organization is enforced by a partial unique index. Owner-password reauthentication and TRANSFER confirmation are required to promote a verified active member while demoting the former owner to admin. Lock tenant before users, with stable ordering for multiple locks; conditional updates reject races in addition to PostgreSQL row locks. Ordinary role/removal routes cannot modify the final owner.
- **Deletion**: Lock all associated tenants in stable order before the global identity. Reject any active owner membership, then remove every membership and recovery token, revoke all sessions, cancel/redact personal mail/invitation data, and pseudonymize the identity. Minimal reference-safe tombstones remain; no complete-erasure/legal-compliance claim.
- **Verification**: 92 backend tests on SQLite/PostgreSQL, seeded migration/session/suspension preservation, transfer-vs-transfer/removal/demotion checks, 24 frontend components and 9 Chromium/SMTP journeys. Full Docker rebuild/migration/storage checks pass locally. Production provider and remote CI remain pending.

## ADR-019: Tenant-Scoped Adjacency Folders and Shared-Workspace Permissions
- **Decision**: Store folder metadata as an adjacency list with stable UUIDs and a composite parent/tenant foreign key. Folder moves update the parent while descendants preserve identity. Normalize display names with NFC/trim and compare case-folded keys; enforce separate root and child uniqueness. Reject self/descendant moves, invalid names and depth above 64, including moved subtree height.
- **Concurrency**: Serialize structural writes with a PostgreSQL tenant-row lock before graph reads, then recheck current verified membership. SQLite development/tests acquire BEGIN IMMEDIATE. Database indexes/checks back service validation. Bounded ancestor traversal supplies breadcrumbs; a bounded recursive CTE measures subtree height.
- **Permission foundation**: All verified active members read shared workspace folders and create at root. Folder creators and current owners/admins rename/move and write into parent folders. Central service checks apply on every mutation; returned can_write is UI guidance. Granular viewer/editor/private/shared ACLs remain Phase 12, deletion/trash Phase 13.
- **Ownership/retention**: Folders are organizational content. Creator account deletion preserves metadata and a pseudonymous identity reference; managers retain stewardship. No file bytes are stored in this table. Migration adds folders without altering existing accounts and refuses populated downgrade instead of silently losing data; back up before upgrading.
- **Verification**: 113 backend tests on SQLite/PostgreSQL, real folder migration preservation/downgrade checks, concurrent cycle/name protection, 28 frontend tests, 11 Chromium journeys, build/lint, Docker migration/schema and actual folder/storage API checks pass locally. Remote CI and production provider/security checks remain pending.

## ADR-020: Pending File Metadata and Organization Ownership
- **Decision**: Store metadata separately from object bytes, with stable UUID, authenticated tenant/creator, nullable folder/root, normalized display/key, declared size/type and timestamps. Add composite folder/tenant FK, separate root/sibling uniqueness and tenant/folder/creator indexes. Files and folders have independent name namespaces.
- **Trust boundary**: Pending is the only current state. Declared attributes are unverified, never availability or scan/preview/download evidence. Reserve metadata internally; expose only read/list APIs until Phase 6 implements upload completion/object validation. Future lifecycle migration must expand states and introduce trusted object attributes and storage references deliberately.
- **Ownership**: The organization owns content; created_by records provenance. Verified active members read, creators/managers receive future write authority. Internal reservation checks destination-folder authority after the shared tenant lock. Creator removal/deletion preserves metadata and manager stewardship.
- **Tradeoffs**: Keep the same Unicode/name policy as folders, unique per file folder/root. Declared sizes accept nonnegative JavaScript-safe integers (maximum 9007199254740991) rather than lose numeric precision in clients; database storage is BigInteger. Actual upload size/quota/MIME/cleanup policies come with later storage/upload phases. Internal reserve currently commits one metadata transaction; the upload phase must coordinate this with upload-session creation and object lifecycle.
- **Migration/verification**: 006_files preserves existing folders/accounts; empty downgrade/re-upgrade succeeds and populated downgrade is refused. 131 backend tests pass on SQLite/PostgreSQL, 31 component tests and 11 Chromium journeys pass, with Docker schema/storage smoke. No remote CI or production readiness claim.

## ADR-021: Tenant-Scoped S3 Adapter and Private Development Bucket
- **Decision**: Use an async ObjectStorage protocol with Boto3 S3 implementation; run blocking operations on executor threads, use Signature V4, configured addressing style, bounded connection/read timeouts and at most two attempts. Use UUID-only tenant/file/object keys and reject foreign adapter scope before provider calls.
- **Operations**: Bucket check, conditional small create (If-None-Match), HEAD, bounded ranged read with observed ETag, and idempotent local delete. Internal byte helpers cap at 1 MiB; large user transfers require future presigned URLs. Check returned length and close streams, including when awaiting tasks are cancelled. ETags are not guaranteed cryptographic content hashes.
- **Trust/ownership**: Resource services authorize membership/file access before constructing refs. The adapter does not accept arbitrary keys and exposes no public route. Scope is a defense layer, not provider IAM. Actual object attributes do not establish malware/MIME safety or file readiness.
- **Configuration**: Private local bucket setup, complete Compose settings and redacted credentials. Custom endpoints require explicit credential pairs and HTTP(S) origins; production custom endpoints require HTTPS/non-default local password. Native AWS may use the SDK credential chain. Production needs least-privilege/provider-public-access controls and maintained storage.
- **Tradeoffs**: No new migration or persisted object references yet; upload phase coordinates DB/session/object lifecycle. SDK cancellation cannot stop committed writes, and lost acknowledgement can make retry conflict; reconcile actual state. Versioned bucket deletion requires explicit later lifecycle/version handling. Normal readiness remains database-only; operator smoke checks storage.
- **Verification**: 158 backend tests with SQLite/PostgreSQL and actual MinIO, including 24 storage unit/contract and three disposable-bucket integration tests. Docker adapter/private-access smoke passes. Initial Docker export interruption was recovered and affected tests rerun. No remote CI or production provider certification.

## ADR-022: Conditional Checksummed Direct Upload and Verified Completion
- **Decision**: Reserve pending file/object/bucket/request identity and expiry transactionally, then return a short-lived presigned PUT. Sign byte count, canonical SHA-256, application/octet-stream and If-None-Match. Browser sends file bytes directly without CloudVault credentials/referrer; public signing host is configured separately from the internal inspection endpoint.
- **Completion**: Check current verified membership, original creator and parent authority under tenant serialization; inspect provider size/checksum/type before committing uploaded fields. Idempotent completion and conditional replay reconciliation handle lost acknowledgements. Uploaded means stored integrity verified, never scan/MIME safety. Clients cannot supply verified facts or choose object identity.
- **Limits**: Default 100 MiB, 15-minute grants and 5-minute completion grace, with persistent identity/IP rate limits. Reticketing confirms the original checksum and does not extend the window. Issued storage capabilities survive app revocation until expiry, but unauthorized completion is refused. Expired pending names/abandoned objects await Phase 9 cleanup; multipart/resume, quotas, scans and download remain subsequent work. Browser full-buffer hashing is bounded by the basic cap.
- **Migration**: 007_uploads preserves old pending metadata, adds coherent upload/verified constraints and creator-scoped idempotency uniqueness, and rejects downgrade that would discard references. No file bytes enter PostgreSQL. Completed organizational content survives creator deletion.
- **Verification**: 174 backend tests on SQLite/PostgreSQL with actual MinIO, 39 frontend tests and 12 Chromium/SMTP/storage journeys pass. Real signed transfers enforce length/checksum/conditional headers, current permission tests and seeded migrations pass, and Docker API/SMTP upload smoke succeeds. The browser waits for destination rendering and uses validated explicit bucket cleanup when Windows stops its Python server. Remote CI and production provider checks remain unrun.

## ADR-023: Shared Frontend Shell and Visual Language
- **Decision**: Wrap authenticated routes in one AppShell with workspace identity, active route navigation, account actions and a skip-to-content link. Use a shared AuthLayout for sign-in, registration, recovery, account actions and invitations. Keep API/session/permission behavior in the existing services and feature components.
- **Visual language**: Neutral surfaces, violet accents, consistent spacing and rounded controls; local SVG icons distinguish files, folders, navigation and uploads. Folder/file lists, real upload stages, pending/uploaded badges and empty/error states remain connected to real data. No simulated usage metrics or future-feature controls are introduced.
- **Responsive behavior**: Sidebar becomes compact navigation on narrow screens; account actions remain available. Forms and rows reflow, keyboard focus remains visible, and reduced-motion preferences are respected. Fonts use the local system stack without a third-party font request.
- **Verification**: Frontend unit tests, lint/build and disposable browser journeys cover existing account/workspace/folder/upload behavior plus navigation, active-route state, mobile sign-out and horizontal overflow. Local desktop/mobile screenshots support visual inspection; this is not a complete accessibility certification.

## ADR-024: Checked Direct Attachment Downloads
- **Decision**: Issue a short-lived signed GET only for uploaded files after tenant-scoped lookup, current verified membership, folder/bucket checks and actual provider size/SHA-256/ETag/type comparison. Recheck membership after provider inspection and signing. Use existing identity/IP rate counters in a separate download-grant category.
- **Delivery**: Signed attachment filename with ASCII fallback/RFC 5987 Unicode, generic octet-stream and no-store provider response; no-store API ticket. Native browser navigation with no-referrer and a scoped session-generation guard keeps bytes out of SPA/API memory and adds no CloudVault bearer header. No grant URL is persisted and issuance is not a delivery event.
- **Tradeoffs**: All current workspace members share read access; private ACLs are Phase 12. Files remain unscanned. Issued capabilities are reusable until expiry (default five minutes, maximum fifteen); logout/removal cannot instantly revoke them or cancel a native transfer. HEAD cannot eliminate out-of-band replacement between check and GET; object version pinning remains later work. Production provider/browser compatibility and other deployment gates remain unverified.
- **Verification**: 186 backend tests on SQLite/PostgreSQL with real MinIO, 42 frontend tests, 13 Chromium/SMTP/storage journeys and Docker actual upload/download smoke pass. No schema changes detected by Alembic. Remote CI/production certification remain pending.

## ADR-025: Checksummed Multipart Transfer and Provider Receipts
- **Decision**: Keep control in MultipartService and bytes on signed direct UploadPart requests. Persist the private provider upload ID, deadline, fixed part size/count and upload state on File; persist declared part hashes/sizes and independently inspected receipts in upload_parts. Original creator and current parent/workspace authority govern all mutations under tenant serialization.
- **Integrity**: Sign per-part length/SHA-256, inspect ListParts, compare every declaration, complete conditionally with If-None-Match and verify HEAD. AWS SHA-256 multipart uses COMPOSITE: base64(SHA256(concatenated binary part digests)) with provider suffix -N. Store the base64 digest with explicit sha256-composite kind/count; downloads reconstruct the provider field. Never label it a whole-file checksum. See [AWS checksum documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html).
- **Bounds**: Default 1 GiB/8 MiB/one-hour deadline, configuration up to 5 GiB/5–32 MiB/two hours, maximum 1024 parts. Sequential chunk hashing and transfer avoid whole-file buffers. Part grants use the shorter of URL duration and remaining deadline. Three browser attempts reconcile provider acknowledgement before re-granting; same-form retry can skip confirmed parts.
- **Failure semantics**: Database/provider commits are not atomic. Known initialization failure attempts provider abort; completion retries reconcile existing verified objects. Explicit cancellation records aborted state while retaining reserved metadata/name. Unknown create acknowledgements, abandoned sessions, concurrent in-flight abort cleanup and reload-based resume remain Phase 9 work. No automatic production lifecycle or resume claim is made.
- **Migration**: 008_multipart defaults existing records to basic/sha256, adds coherent transfer-state constraints and part receipts, and refuses downgrade while any multipart record exists. Restore a pre-upgrade backup for rollback that cannot represent this state.
- **Verification**: 197 backend tests on SQLite/PostgreSQL with actual MinIO, 49 frontend tests, 14 Chromium/SMTP/storage journeys, lint/build and rebuilt Docker SMTP/basic/multipart upload/download smoke pass. Live Alembic schema check is clean at 008_multipart. Remote CI and production certification remain pending.

## ADR-026: Reconciled Resume and Durable Upload Cleanup
- **Resume**: Progress inspects actual provider parts and updates receipts under the existing tenant/creator/parent authority lock. It returns confirmed byte count/declarations/deadline without URLs. Resume requires the original checksum manifest, reconciles provider progress and grants only missing chunks. Chunk size/deadline remain fixed; reload resume requires reselecting the original file and resumes at part boundaries. Confirmation/completion can use the existing grace; grants cannot extend authorization.
- **Cleanup**: The privileged periodic worker operates only on the configured unversioned bucket. Expired pending uploads wait for completion grace plus a settling interval. Known uploads are aborted, objects deleted and absence checked before names are released. Hidden File tombstones retain object references and are revisited for late writes/provider retries. Completed files and unexpired sessions are excluded; errors retain references/names and rotate attempts. Partial unique indexes exclude only cleanup tombstones; normal duplicate-name protection remains.
- **Initialization**: Commit UploadIntent before provider CreateMultipartUpload, with immutable server UUIDs, payload fingerprint and fixed deadline. It deliberately has no account/file FK so failed transactions or future account deletion cannot remove the exact cleanup key. Failed initialization may leave no visible file, but the intent remains. Retry uses the same identities/window and rejects changed metadata. The worker uses exact-key inventory to reclaim any IDs created before a lost acknowledgement.
- **Provider boundary**: Local MinIO broad prefix listing is not a reliable inventory and empty-prefix inventory is an in-memory cache; a restart loses that cache. Exact-key listing uses persistent provider metadata, hence durable intents are required. The supplemental broad scan accepts only canonical CloudVault UUID keys, waits beyond the maximum session/grace and skips known sessions. Its cursor is held by the worker and restarts from the beginning after restart. Historical untracked keys may still need provider lifecycle cleanup. See [pinned MinIO source](https://github.com/minio/minio/blob/7aac2a2c5b7c882e68c1ce017d8256be2feea27f/cmd/erasure-server-pool.go).
- **Retention/rollback**: Cleanup metadata/intents are retained rather than claiming immediate physical erasure. 009_upload_cleanup preserves prior file/account data and refuses downgrade that discards either cleanup tombstones or initialization intents. Database backups cannot restore reclaimed object bytes; object backups require a separate provider plan. Version-aware cleanup must be implemented before enabling bucket versioning in Phase 14.
- **Development lifecycle**: Compose explicitly sets local stale-upload expiry to 24 hours and scan interval to one hour. This is a local safety net, not production S3/R2 lifecycle configuration or a measured 24-hour execution guarantee. Actual app cleanup and provider aborts are tested; the full lifecycle waiting period is not exercised.
- **Verification**: 206 backend tests on SQLite/PostgreSQL with real MinIO, 53 frontend tests, 14 Chromium journeys, lint/build and Docker SMTP/upload/progress/resume/download checks pass. Live schema is 009_upload_cleanup with no drift; maintenance worker and one-shot tick succeed. Actual reclamation/lost-initialization cleanup is verified in disposable integration fixtures. Remote CI/production verification remain pending.

## ADR-027: Tenant-Scoped Literal Filename Search
- **Decision**: Add a dedicated search service and GET /api/v1/files/search for current verified workspace members. Apply tenant and non-cleaned predicates to every query before filters/pagination. Search NFC-normalized, trimmed, case-folded filename keys using literal substring matching; escape SQL LIKE wildcards. Whitelist sort/filter values through a strict query model. No raw SQL ordering, regex, fuzzy matching or file-content search is accepted.
- **Result contract**: Return existing public file metadata plus direct folder name, joined on both folder and tenant identity without one lookup per result. Current workspace members share read access under existing policy. Downloads use the existing checked ticket service. Search returns no-store and no object/provider/cleanup identity; Phase 12 must apply resource ACLs before search pagination and folder metadata exposure.
- **Filters/order**: Workspace/root/direct-folder scope, status, transfer method, creator UUID, exact declared MIME, and declared byte range. Uploaded size equals declared size through existing integrity constraints; pending values are declarations. Sort by case-folded name, size, created or updated timestamp, with UUID tie-breaker in the same direction. Offset is bounded at 10000; default page 25, API maximum 100, with limit+1 rather than a full count.
- **Indexes**: Partial tenant B-tree indexes for name/size/created/updated and status/name; PostgreSQL partial GIN on name_key with gin_trgm_ops. 010_file_search installs pg_trgm if missing and leaves the shared extension on rollback. SQLite creates the B-tree indexes and omits only the PostgreSQL-specific GIN in DDL/schema comparison. See [PostgreSQL pg_trgm documentation](https://www.postgresql.org/docs/16/pgtrgm.html).
- **Bounds/tradeoffs**: A separate persistent search budget permits 1200 identity/4800 IP requests per configured rate window (15 minutes default). Short/common substring terms may scan extensively; GIN does not guarantee a plan for every query. Synthetic 5001-row PostgreSQL checks validate selective GIN and size-order index use after statistics update/pending-list maintenance, without forced planner settings or fabricated throughput. Production workload/statement-timeout/abuse review and query-plan monitoring remain gates. Offset pages are not a consistent snapshot under concurrent changes.
- **Client**: A search navigation/page and folder shortcut submit filters explicitly, reset pagination, use 5/25/50 rows, show folder context and preserve native downloads. Query keys include workspace/user/all submitted filters/page; request cancellation/session-generation guards and workspace remounting reject stale results. Search values are not persisted to local storage. GET parameters may appear in operational access logs; review query logging/redaction before production.
- **Verification**: 214 backend tests on SQLite/PostgreSQL with real storage, 60 frontend tests, 15 Chromium journeys, migration/schema/index-plan checks, lint/build and rebuilt Docker search/filter/order/page/transfer/maintenance smoke pass at 010_file_search. Remote CI/production load/provider checks remain pending.

## ADR-028: Revocable External File Capabilities
- **Scope**: Completed-file share links, 1–720 hour expiry (24 default), optional 8–128 character password, metadata-only access and optional 1–10000 download-grant cap. Current verified file creators/managers manage links; recipient account identity, folder sharing/private ACLs/previews are separate features.
- **Secrets**: Random 256-bit link token with SHA-256 lookup, Argon2 password hash, no raw persisted secret. Return the link once using a fragment; public POST proof omits account cookies/Authorization and the SPA clears the address fragment. No-store/no-referrer includes failures. Production HTTPS/body logging/proxy/CPU-abuse review remains required.
- **Authorization**: Public file lookup binds link file and tenant; current active verified publisher creator/manager authority is required. Removing members, role updates, ownership transfer and account deletion permanently revoke affected links in their existing transactions. Logout alone does not revoke links. Future Phase 12 ACLs must replace the current resource authority consistently.
- **Storage**: A factory opens the tenant-scoped adapter only after public proof succeeds; it does not require an account JWT or accept a caller tenant. Common DownloadService checks configured bucket and actual HEAD size/checksum/ETag/type before signing attachment GET. Normal member downloads retain membership rechecks during provider operations.
- **Ordering**: Tenant lock protects public grant state through provider inspection/signing and counter commit, serializing revocation and membership changes. SQLite public handling uses BEGIN IMMEDIATE. This has an explicit throughput cost, without a performance claim. Provider errors do not count; lost acknowledgement after commit does. One issued URL can be reused; counters are grants rather than delivered bytes/downloads.
- **Bounds**: Public access/download share persistent 100/IP and 100/capability budgets per configured window (15 minutes default); create/revoke use normal category limits. Grant URLs use normal download TTL/remaining share deadline, recalculated after provider inspection, with provider clock/signing-resolution limits. Revocation cannot recall issued URLs or received bytes.
- **Retention/rollback**: 011_sharing adds metadata without altering existing accounts/files. Listing never returns hashes/raw links; no secret recovery/purge claim. Empty downgrade is permitted; populated rollback refuses and requires a pre-upgrade backup. File/object retention and SQL/provider backup limitations remain.
- **Verification**: Backend, database, frontend, real anonymous-browser and Docker evidence is recorded in CONTINUE.md and docs/phases/phase11.md. Tests exposed and corrected a login-dependent public storage adapter and stale same-tab capability state. No remote CI/production certification is claimed.

## ADR-029: Resource-Local Grants and Mandatory Ancestor Boundaries
- **Policy**: Preserve existing workspace visibility by default; private File/Folder reads require creator/current workspace manager authority or a ResourceGrant viewer/editor entry. Every containing folder must also be readable. Trusted owners/admins retain broad management. Grants are resource-local with no inherited editing and no ambiguous explicit-deny precedence.
- **Enforcement**: PermissionService supplies local read expressions and a recursive readable-folder CTE bounded at depth 64. Public search/file/folder lists filter before offset/limit+1 and context; direct IDs, breadcrumbs and transfers require effective read. Editor flags load in a bulk page query rather than per result. No new production performance claim follows from prior synthetic search-index checks.
- **Delegation**: Viewers read/download. Editors rename completed files/folders and create content within an editable folder. Creators/managers own permission updates, folder moves and external publication; resource grants cannot escalate workspace membership roles. Creator access remains subject to ancestor boundaries. Moves may change effective read scope and revoke subtree external links; object bytes/keys are unchanged by rename.
- **Consistency**: Permission writes acquire tenant serialization, recheck management and target active verified membership, and commit with affected file/subtree share revocation. Grant upserts remain unique under concurrency. Member removal explicitly deletes workspace grants; account deletion cascades via membership. Public shares recheck publisher effective file access; ordinary downloads recheck ACLs during provider inspection/signing. Existing provider capabilities/received bytes cannot be recalled.
- **Schema/rollback**: 012_permissions adds default workspace visibility and a membership-bound, exactly-one-resource grant table with checked viewer/editor roles and partial uniqueness. Existing account/content rows remain. Downgrade refuses private policy or grants instead of silently widening access; rollback may require a pre-upgrade backup. Historical migration fixtures seed old-schema rows directly and restore head after guarded chain downgrades.
- **Client/limits**: Resource pages expose visibility and paginated member/grant controls. Caches/remounts include workspace/user/resource. Grant revocation does not override workspace or implicit rights. Permission mutations permit 100 identity/500 IP per configured window; rename uses normal categories. Previously received metadata can remain cached until refresh. Recursive path/query cost, timeout/abuse review, resource audit/history, groups/custom roles, realtime synchronization and representative load remain future/deployment work.
- **Evidence**: SQLite/PostgreSQL, browser, frontend and rebuilt Docker checks are recorded in CONTINUE.md/docs/phases/phase12.md. No remote CI/push or production certification is implied.

## ADR-030: Batch Trash, Original-Location Restore and Durable Purge
- **Scope**: Completed-file/folder soft deletion with fixed 30-day retention and current creator/manager/ancestor authority. Trash/restore also require writable original parents. Mixed-creator subtrees need a manager; pending uploads must finish or clean first. Tenant-scoped listings apply effective trash read/management before union pagination.
- **Batch model**: File/Folder trash_id references a root TrashEntry with server-owned retention/not-before times, irreversible purge intent, restore/completion and fair-attempt markers. Mark active descendants only; restore the batch without reviving older independent trash. Live names exclude trash, and atomic restore rejects conflicts rather than renaming/overwriting or moving to a less restrictive location.
- **Authorization**: Live ACL predicates exclude trash, protecting browsing/search/context/transfers/publishing. Preserve visibility/grants/creator/object identity on restore; lifecycle-removed grants and revoked external links never reactivate. Confirmed permanent folder deletion includes nested independent trash. Previously issued provider GET capabilities and received bytes retain their lifetime.
- **Irreversibility**: Explicit DELETE-confirmed request or expired retention commits purge intent under tenant serialization before provider effects. Restore/purge races have one outcome. Cleanup reacquires the lock, waits beyond original upload expiry/grace/settle, aborts exact-key multipart remnants, deletes and confirms absence. Versioned/suspended buckets and drift/provider failures fail closed. No synchronous erasure or exact deletion-time guarantee.
- **Maintenance**: Existing Compose upload-cleanup invokes cleanup_trash ticks; optional standalone --once is available. Process up to 10 batches/up to 10 file references each, rotate attempts and retain exact references after success for late-write rechecks. Restored batches are skipped. Metadata/names/grants/revoked link/history retention remains internal; this is not legal-compliance or complete-erasure certification.
- **Migration**: 013_trash preserves existing active data, changes live-name uniqueness and retains cleanup references. Any trash history refuses downgrade, including restored batches; recover via pre-upgrade backup for unrepresentable rollback. Database backups do not recover purged provider bytes. Phase 14 must implement version-aware lifecycle before enabling bucket versioning.
- **Verification**: Unit/API, actual object deletion/retry, SQLite/PostgreSQL migration/concurrency, frontend/browser and Docker evidence is recorded in CONTINUE.md/docs/phases/phase13.md. Initial tests caught a legacy folder name precheck that still counted trash; final logic excludes it consistently. Browser tests wait for the target folder before choosing a file. No production load, remote CI or public-provider certification is implied.

## ADR-031: Immutable Application Versions and Optimistic Content Selection
- **Identity**: Preserve a logical File's name, location, provenance and ACL while FileVersion retains each exact immutable UUID object key and verified content snapshot. Backfill existing basic/multipart uploads as version 1 without copying bytes. Current content metadata remains on File for existing search/download/share consumers.
- **Concurrency**: Per-file numbers identify content; a separate monotonically increasing generation orders changes, including restoring A after B. Replacement completion checks its original base generation under tenant serialization. A stale candidate never becomes current. Completed request replay returns current metadata without reactivating its version. Upload/restore events retain actor, generation and reason.
- **Authorization**: Current effective read gates every history operation. Editors/creators/managers with writable parents can replace or restore; only the candidate uploader can complete. Trash hides history. Each content change revokes external links atomically. Reader downloads verify the chosen snapshot and recheck current authority; issued URLs keep their original object key and cannot be recalled.
- **Transfers**: Replacement PUT uses existing basic cap, canonical SHA-256, conditional creation and original URL/deadline/grace semantics. Basic/multipart original history works; multipart replacement and persistent version-upload reload resume remain explicit follow-ups. At most 10 not-yet-cleaned pending candidates per file. Original transfer controls refuse files after any version transition.
- **Lifecycle**: All pending/completed refs participate in trash not-before and purge. Pending-version maintenance waits original deadline/grace/settle, confirms absence and retains refs for late writes. Old multipart initialization cleanup recognizes retained version refs even after current metadata changes. Trash rotates bounded version attempts and cannot complete while any scoped content ref remains unresolved. SQL backups do not recover reclaimed object bytes.
- **Accounting**: Sum each completed retained snapshot once, independent of current selection; pending declared bytes remain separate until confirmed cleanup. This prepares quota enforcement without claiming aggregate quotas or provider billing reconciliation. No individual-version delete, pruning or retention automation is implemented.
- **Provider**: Keep buckets unversioned. Enabled/Suspended maintenance fails closed; application snapshots do not implement provider VersionId/delete-marker lifecycle. Enabling provider versioning requires a separate verified lifecycle decision.
- **Migration**: 014_versions adds snapshots/events and current number/generation, preserving existing completed/trash/purge metadata. Any additional candidate or change event guards downgrade, including cleaned candidates. Revert from a pre-upgrade backup when old schemas cannot represent retained refs.
- **Validation**: API/concurrency, migration/backfill, real basic/multipart bytes and all-version purge, frontend/browser and Docker checks are recorded in CONTINUE.md/docs/phases/phase14.md. No remote CI, production provider certification or load benchmark is implied.

## ADR-032: Explicit Limitations Ownership and Release Gates
- Historical phase reports remain snapshots; docs/LIMITATIONS_BACKLOG.md is the current cross-phase closure register. Repeated limitations are consolidated and resolved items separated from open work, optional product decisions and intentional constraints.
- Add 14A version completion and 14B core library recovery before 15; 18A collaboration completion/scope decisions before 19; 22A lexical/navigation/pagination completion before 23. Original phase numbers are preserved. Existing phases receive named limitation IDs and acceptance evidence requirements.
- Scheduling is not implementation or certification. Remote CI evidence remains an immediate separately authorized push/dispatch gate; provider selection precedes provider integration certification, and public release requires actual SMTP/storage/security/paired recovery/load evidence.
- Each new phase must close or explicitly carry its assigned IDs, record new gaps with a checkpoint, and preserve deliberate capability/SMTP/cleanup/retention boundaries. Security or data-loss defects block progress immediately regardless of the scheduled checkpoint.

## ADR-033: Durable Version Transfers and Lease-Aware History Pruning
- **Transfer identity**: Commit FileVersion plus VersionPart declarations before provider multipart creation. The candidate/key survives lost creation acknowledgement. Retry reconciles exact-key multipart IDs, keeps the original manifest/deadline and never mutates the old current object. Shared MultipartService primitives verify signed parts/provider receipts; only the candidate uploader with current resource/parent authority can manage/complete it.
- **Activation**: Provider final size/composite checksum/octet-stream/ETag verification and the original generation gate precede current-version selection. Retry/progress reconcile provider truth; completion remains idempotent and cannot reactivate old history. Empty versions use basic upload; larger replacements choose bounded multipart hashing.
- **Resume**: Secret-free, user/workspace/file-scoped tab session manifests survive reload; server pending history also supports original-file re-selection and resumed grants. No file bytes, account/storage secrets or presigned URLs enter the manifest. Part discovery validates hashes and returns only missing grants without extending deadlines. Pause stops the client; cancellation is a separate durable server transition.
- **Cancellation**: Commit cancelled_at before best-effort provider abort. Pending basic/multipart candidates can no longer activate. Cleanup retains their exact references and waits original expiry/grace/settle, confirms known multipart termination and object absence, and rechecks late writes. Completion/cancel serialize to one outcome.
- **Pruning authority**: Current file creator/managers with writable parents may explicitly queue completed non-current history deletion or configure retention. Editors may replace/restore but cannot directly delete history or change policy. Pending candidates use uploader-only cancellation. Prune requests cannot be undone; new restore/download grants stop immediately.
- **Retention policy**: Per-file nullable keep-last setting retains the newest N available completed snapshots plus current if older; current content is always protected. Apply after activation/configuration and through bounded worker policy sweeps (25 files, up to 100 queue candidates/file per tick). Disabling changes future selection, not committed deletion intent.
- **Lease safety/accounting**: Pruning waits original upload authorization/grace/settle and the maximum previously issued 900-second download lease plus settling delay. Trash cleanup respects any later prune deadline. Retained/pending usage changes only after confirmed removal; failed deletion retains refs/usage and rotates retries. Uploaded prune references are rechecked for late bytes. Aggregate quotas and full audit/metadata retention remain Phase 19/20 work.
- **Storage/rollback**: Provider bucket versioning stays disabled; Enabled/Suspended maintenance fails closed. 015_version_transfers preserves initial snapshots and adds part receipts, cancellation/prune markers and nullable retention settings. Any version transfer receipts, cancellation/pruning history or active policy refuse lossy downgrade; paired DB/object recovery remains a production gate.
- **Scope/verification**: L02/L03 and L04 core lifecycle are Phase 14A work; current evidence and inherited/future limitations are recorded in CONTINUE.md and the phase report once verification completes. No remote CI, provider-wide production certification or throughput claim is implied.

## ADR-034: Atomic Library Movement, Explicit Recovery and Durable Original Cancellation
- **Movement**: Completed files can move only under tenant serialization with creator/manager authority, writable source/destination parents and a matching expected source_folder_id. Location changes revoke external links without changing object/version identities, content generation or resource-local grants. Stale source changes/conflicts fail atomically; pending/version operations still recheck live current authority.
- **Recovery**: Keep original-location restore backward compatible; add explicit active writable destination/name selection. Original readable trash authority remains mandatory, but the old parent need not be active. Folder recovery checks subtree ownership, full height (including older independent trash), cycles and namespace constraints. Update root location/name and clear only that batch atomically; older trash stays trash. Purge/restore serialize to one outcome.
- **Cancellation before trash**: A separate literal CANCEL UPLOADS action cancels at most 100 live pending original records and trashes the folder in one transaction. Mixed creators require managers. Durable upload_cancelled_at and multipart aborted state deny later completion/grants after restore; no provider side effect occurs before commit. Outstanding URLs retain their original deadline, and existing original/trash maintenance aborts/deletes/confirms exact refs after grace/settle. Pending refs block completed purge until absence is proved; tombstones support late-write retries.
- **Legacy discard**: Literal DISCARD and creator/manager/writable-parent authority can tombstone pending metadata only when object/session, FileVersion and UploadIntent references are absent. Preserve the row and release its live name; never invent bytes, erase a cleanup ref or override contradictory retained intent. Such contradictions fail closed for operator reconciliation.
- **Migration/limits**: 016_library_recovery adds the pending-only cancellation marker and permits no-reference cancelled legacy cleanup tombstones. Downgrade refuses cancellation/discard history. UI destination pages use 25 records; full subtree/tenant-lock cost and the 100-pending bound require L33 scale validation. Aggregate quotas, complete audit/metadata retention, realtime, production provider/security/paired recovery and remote CI remain their separately tracked checkpoints.

## ADR-035: Verified Transient Previews and Credential-Free Native Rendering
- **Content binding**: Preview a retained completed immutable version only under current membership/file/all-ancestor read authority. Compare HEAD size/ETag/octet-stream/basic or composite digest, conditionally read at most 10 MiB and fully rehash it. End the initial transaction and recheck live authority/prune/trash and default current generation before returning. No source/derivative bytes enter PostgreSQL.
- **Output**: Strict UTF-8 becomes escaped text; binary controls fail and format/bidi controls become visible. Actual supported image/PDF parsing produces fresh static PNG pixels, stripping metadata and omitting PDF form/annotation drawing. No original active HTML/SVG/PDF/video embedding. Unsupported/oversized content retains authorized original download fallback. Detection is transient and never a scan/safety label.
- **Isolation**: Native jobs run in a separate network-disabled non-root read-only Compose container without application credentials/data mounts, using an IPC-only volume. Drop capabilities, set no-new-privileges, CPU/memory/PID/temp limits and fresh per-job CPU/address-space/file-descriptor/time/output bounds. No API-process host fallback; direct Windows native support requires isolated deployment. Container restrictions mitigate risk but require actual smoke/security verification.
- **Resources**: 10 MiB source, 16M image pixels, 1600 edge/1 MiB PNG; up to 1000 source PDF pages/first 100 browsable; text first 65,536 characters. Two API source jobs/process, one native job. Rate limits and explicit retry bound development work; production load/abuse tests remain L29/L33.
- **State/rollback**: On-demand output is transient, authenticated, no-store, version-bound and never cached persistently. Browser blob cleanup and stale-response guards apply. No new schema/object refs/readiness state or migration; existing schema stays 016_library_recovery. Quarantine/scanning is Phase 17. L38 assigns bounded video/queued derivative jobs and invalidation to 16/26/27; no full preview coverage is claimed.
- **Verification**: Local SQLite/targeted/frontend checks are recorded in docs/phases/phase15.md. Actual Docker isolation/native/live API/provider smokes pass. Browser run is 21/22; final PostgreSQL/provider regression passes 306 tests; final browser rerun remains open after Docker was closed and restart hit the socket error again. Production parser isolation/patching/abuse review is mandatory before release.
- **References**: Pillow security guidance https://pillow.readthedocs.io/en/stable/handbook/security.html ; PDFium helper APIs https://pypdfium2.readthedocs.io/en/stable/readme.html . Source declarations do not establish format or safety.

## ADR-036: Durable Maintenance State Behind Private Celery Queues
- 2026-10-16: Phase 16 queue foundation reuses existing email/upload/version/trash services. Celery Beat emits argument-free maintenance hints to private JSON-only queues. PostgreSQL outbox/resource refs remain authoritative; Redis AOF is operational persistence, not an exactly-once transaction guarantee.
- Atomic background_jobs claims use UUID ownership and expiring leases. Stale owners cannot overwrite a replacement checkpoint. Source-bound orphan cursors commit only after successful invocation, survive broker/process restarts and reset on endpoint/region/bucket changes. Source credentials, action tokens and bytes never enter queue payloads.
- Per-task NullPool engines avoid asyncpg/event-loop/fork reuse. Configure 150/180-second soft/hard task bounds, a minimum 240-second/default 300-second DB lease, 600-second broker visibility, late ACK, worker-loss redelivery, prefetch one and bounded sanitized retries. Existing per-resource locks/deadlines/confirmed absence remain mandatory.
- Health reports execution freshness/lease/failures and operator stage/backlog/dependency observations (extended by ADR-038), explicitly not backlog completion or successful SMTP/provider effects. Real worker/provider fairness and failure evidence remains required before Phase 16 closes. L37/L38 reconciliation/video jobs also remain assigned to this phase.
- 017_background_jobs contains operational state only; no file bytes/user cleanup references move. Stop scheduler/workers before downgrade; active leases guard it. Losing an inventory checkpoint restarts scanning, not destruction of retained refs. Only disposable SQLite migration/unit evidence currently exists; live PG/Redis/prefork/failure checks remain open.
- User explicitly deferred Phase 15 final browser verification and continued development. This is a specific sequencing exception, not a completed Phase 15 or general permission to skip acceptance. Neither Phase 15 nor Phase 16 is marked complete.
- References: https://docs.celeryq.dev/en/stable/userguide/configuration.html and https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html . See docs/phases/phase16.md for limits and evidence.

## ADR-037: AWS S3 as the Production Compatibility Target
- User selected AWS S3 on 2026-10-16; MinIO remains local development only. Target private unversioned S3, immutable application object keys, SHA-256/composite verification and conditional writes consistent with the current adapter. Keep detecting/refusing Enabled/Suspended buckets until complete VersionId-aware cleanup exists.
- L22's provider selection is recorded; actual AWS transfer/HEAD/completion/checksum, pagination, signing/expiry, abort/delete, IAM/encryption/CORS/lifecycle and paired recovery certification remains 26/27/29/31. No AWS credentials/resources/spending were provisioned by this decision.
- Selecting AWS does not implement Object Lock, provider VersionId purge or strict one-use/immediate revocation. Existing presigned capability limits remain; P04 delivery/security decisions are reviewed in 27. Independent backups remain required for unversioned storage.
- References: https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html and https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html . Local provider evidence does not certify AWS.

## ADR-038: Persist Rotation Before Bounded Storage Work
- 2026-10-16: Keep one storage lease/queue and rotate six independent stages: original uploads, initialization intents, orphan inventory, policies, versions and trash. Persist the next turn before provider work; exceptions and killed workers cannot repeatedly starve later stages. Record interrupted attempts on lease reclaim and fence completion with the lease UUID. Preserve orphan position across unrelated stages and failed attempts; reset on provider namespace changes.
- Each stage selects at most STORAGE_STAGE_BATCH_SIZE records (default 5, allowed 1–10); orphan inventory uses one provider page of that size. Existing per-resource nested limits and task deadlines still apply. Default cadence gives a stage one turn per six minutes under normal completion; no load/latency guarantee is implied. Live worker/provider failure and large-backlog proofs remain open L20 in 16/26.
- Persist only safe stage times/counts/outcomes alongside the private cursor. Operator health requires fresh success for every stage; individual failed/interrupted/deferred work cannot be masked by another successful stage. Orphan failures remain visible until a complete clean inventory cycle. Backlog snapshots count only unconfirmed eligible rows; retained intents are recheck populations, not unfinished bytes. Redis PING and bucket HEAD/versioning probes are non-destructive; no tenant identifiers/payloads/exception text are output.
- API readiness remains DB-only; feature gating and production alerts stay assigned to 28. No SMTP deliverability, empty-provider, exact-once or byte-purge claim follows from a healthy invocation. No additional schema migration is needed beyond operational JSON state in 017. See docs/phases/phase16.md for targeted local evidence and open live acceptance.

## ADR-039: Retained Initialization Scope and Explicit Operator Reconciliation
- 2026-10-16: Migration 018_intent_cancellation adds retained folder_id, scope_recorded and cancelled_at without hierarchy/account foreign keys. New intents authorize parent writes under the tenant lock. Trash includes active unmaterialized subtree intents in the combined 100-transfer cancellation cap and manager-only mixed-creator rule; cancellation survives restore. Recheck cancellation between intent commit and provider creation. Original object IDs/deadlines remain immutable.
- Old intents have unknown scope rather than an invented root/folder. Unmaterialized unknown-scope retries require a fresh request; their retained exact refs still receive maintenance. Materialized original sessions remain governed by their File record. Downgrade refuses recorded scope/cancellation because forgetting it can revive a stale retry; restore a backup instead of removing evidence.
- DB-operator CLI reconcile_upload defaults to read-only paged inventory and never runs provider operations on diagnosis. Explicit --apply and matching --confirm-file authorize one selected target. Pending legacy/unmaterialized retirement persists cancellation, waits every retained deadline/grace/settle, refuses completed/cross-tenant/changed-bucket/versioned references, and confirms exact provider absence before retiring metadata. Provider work is bounded to the configured stage batch plus the intent per pass; global deadline/state checks cover the whole history. Progress and every reference survive failure; repeated sweeps catch late writes.
- Completed retained versions require explicit --adopt-version plus an active verified workspace owner/admin --operator-user. Live folder authority, source size/checksum/ETag/type and retained availability must match before reusing normal version activation, share invalidation and history. Give adoption a new request identity and invalidate the old initialization. Never resurrect cancelled/retired metadata or present a metadata check as a full-byte safety scan.
- Operator inventories contain private object identities; keep them off public routes/logs. This local DB privilege path is not an application-user escalation. No production data reconciliation or schema upgrade was run during implementation. L37 live PG/provider/late-ACK/late-write evidence remains 16/26; L38 queued video/preview work still remains in 16. See docs/phases/phase16.md for evidence and operation.

## ADR-040: Durable Private Preview Jobs and Isolated Video Posters
- 2026-10-16: Preview jobs bind requester, tenant, completed immutable version/page and optional current generation. UUID request IDs deduplicate retries; fixed 15-minute expiry, at most three leased attempts and 20 queued/running jobs per tenant bound work. Beat emits argument-free hints to a dedicated private preview queue/worker. Persist render/cleanup rotation before provider work so hard failures cannot starve the other turn. Existing lease tokens and conditional publication fence old owners.
- Migration 019_preview_jobs stores only identities, times, safe metadata and derivative digest; it also admits the preview heartbeat name. Raw PNG/UTF-8 derivatives stay in private S3 under a preallocated immutable UUID, never PostgreSQL/Redis. Reuse verified source HEAD/conditional bounded read/full digest and current authority before rendering and under the tenant lock before publication. Every fetch checks requester/current membership/ACL/ancestor/prune/trash/generation before and after provider I/O and checks the derivative hash. No public derivative URL or source HTML/video embed is issued.
- Creation/cancellation use 100 identity/500 IP requests per category window; polls 1500/7500. Cancellation fences publication; browser abort best-effort cancels known jobs. Lost responses still expire. Reclamation waits expiry plus lease/settle (25 minutes at defaults), aborts exposure, checks exact absence and retains refs for late writes. Namespace changes block and report cleanup instead of targeting the wrong bucket. L19 explicitly includes derivatives/reservations/ambiguous writes in Phase 19 accounting; L21 retains job/ref metadata policy in 20.
- FFmpeg/FFprobe are installed only in the dedicated credential-free network-disabled renderer target. Supported MP4/WebM H.264/VP8/VP9 input produces one first-frame static PNG, not moving playback/audio. Keep 10 MiB source, 120-second/4096-dimension/8,294,400-pixel video bounds, bounded source probing, 4/5-second subprocess deadlines, existing native CPU/address-space/container/PID/time limits and bounded tmpfs. Whitelist file/pipe protocols; disable MOV external/absolute references; kill decoder process groups at worker exit. No API/queue host parsing fallback.
- A busy renderer is retryable rather than permanently unsupported. Malformed/resource-limited/unsupported inputs retain explicit download fallback and unscanned status. 019 refuses rollback that loses any cleanup ref or an active preview lease. Local lifecycle/contract tests do not certify actual FFmpeg, Linux isolation, Redis/prefork/restart, PostgreSQL, provider behavior or browser acceptance. Docker was stopped and native video tools absent; no engine restart, app migration or deferred Phase 15 browser run occurred. Phase 16 remains open for live acceptance; later L38 provider/browser/security checkpoints remain 26/27.
- Primary references: [FFmpeg protocol whitelist](https://ffmpeg.org/ffmpeg-protocols.html), [MOV external-reference controls](https://ffmpeg.org/ffmpeg-formats.html). See docs/phases/phase16.md for evidence and operation.
## ADR-041: Exact-Version Quarantine and Bounded ClamAV Release

- 2026-10-16: uploaded confirms provider integrity; it does not authorize content release.
  Migration 020 puts all existing File/FileVersion content into pending quarantine and
  cancels pre-existing preview jobs. No old object is grandfathered into release.
- A dedicated private Celery queue scans one immutable version per durable maintenance
  hint. PostgreSQL UUID leases, three attempts, bounded backoff and expiry fence publication.
  Read-only and foreign-tenant users cannot retry. Authorized writers can retry errors;
  blocked/oversized content cannot be manually marked clean.
- Before release, conditional provider reads must match retained size, ETag, octet-stream,
  bucket and full basic/composite SHA-256. Bytes stream in at most 64 KiB chunks to ClamD
  INSTREAM; no file bytes enter PostgreSQL or Redis. A scanner must consume the complete
  verified stream before any verdict can publish. Recheck exact metadata, policy, namespace,
  cleanup/prune state and lease under the tenant lock after scanner I/O.
- Current and historical downloads, share creation/resolution, transient previews and queued
  derivative request/publication/result require the same exact-version release gate. Existing
  signed URLs are capabilities until expiry and cannot be recalled (D01). Previously delivered
  bytes cannot be recalled. Deployment must account for outstanding pre-upgrade capabilities.
- ClamAV runs non-root with a read-only root, dropped capabilities, CPU/RAM/PID/temp bounds,
  a private internal network, no published port and no API/DB/S3 credentials. A separate
  credential-free updater has outbound access and writes the signatures volume; the daemon
  mounts it read-only. Disable concurrent database reload to bound memory on the 4 GiB WSL
  development host. This is defense in depth, not a production sandbox certification.
- Definitions must be at most 24 hours old by default (configuration maximum 48 hours).
  Missing/stale/malformed replies, timeouts, provider changes and hashing failures fail closed.
  Changing the scan-size policy or provider namespace invalidates release and queues a fresh
  scan. Signature updates do not retroactively certify/rescan released bytes; continuous
  rescanning and threat response require explicit later security/operations work.
- Default and maximum supported scanner input is 100 MiB; upload limits remain independent.
  Larger completed multipart content is retained/quarantined and cannot be downloaded,
  shared or previewed. No silent size-limit bypass. Archive limits, encrypted content,
  macros and malformed supported media trigger conservative scanner policy where supported.
  Unsupported detection and antivirus false negatives remain possible: UI says no known
  threats detected and never guarantees safety. Quota/billing for retained quarantined bytes
  is due in 19; provider/security/monitoring/load gates remain 26/27/28/31/32 (L39).
- Rollback refuses retained uploaded content or active scan leases because removing quarantine
  would restore unsafe grants. Use a suitable coordinated pre-upgrade backup, with storage
  recovery separately planned. Never weaken rollback to satisfy historical migration tests.
- Official protocol/deployment references: https://docs.clamav.net/manual/Installing/Docker.html
  and https://docs.clamav.net/manual/Usage/Scanning.html . Local real-engine/queue evidence and
  remaining verification are recorded in docs/phases/phase17.md.

## ADR-042: Authorized Current-State Observations and Shared-Cookie Coordination

- 2026-10-16: Phase18 uses WebSockets to invalidate bounded authorized current views.
  Read existing service-layer pages at a bounded cadence and hash them internally; detect
  committed worker/API changes without adding a publication hook to every writer. Emit
  opaque subscription changes and only the uploader's visible confirmed receipt counts.
  No file names, object keys, raw content, snapshot hashes or access grants enter frames.
  REST remains responsible for current authorization, quarantine and capability issuance.
- This deliberately coalesces transitions. It is not a durable event stream, replay cursor,
  outbox or notification inbox. The cost is repeated DB/service reads per socket/topic.
  L40 requires a Phase20 durable-notification decision, real deployment/browser matrix26,
  security27, alerts28 and measured capacity/fairness32 with any necessary fanout/admission
  redesign. Installing WebSockets does not certify production scale or reliable history.
- Ticket POST requires a verified authenticated actor. Random 20-second tickets are stored
  hashed in Redis, consumed by GETDEL and supplied in the first frame of a strict-Origin,
  query-free socket. Bind user/tenant/session, recheck authority every observation and renew
  the connection capability after five minutes. No long-lived JWTs/tickets in URLs/logs.
- Atomic standalone Redis leases bound global user/IP connections across API processes;
  local process, handshake, command, topic, frame, send and observation bounds limit work.
  No S3/renderer calls are made. End DB transactions before sending; release leases on
  cleanup, with expiry after crashes. Redis failures close the feed and retain REST fallback.
  Multi-key Lua is not a Redis Cluster compatibility claim. Proxy-IP trust requires review.
- Client subscriptions deduplicate, cap at eight and fall back to periodic REST on overflow
  or lost transport. Reconnect resynchronizes current state instead of claiming replay.
  Access loss resets protected caches/local page state and revokes preview blobs. Received
  data and issued signed capabilities retain their existing recall limitations (D01/D02).
- Same-origin Web Locks serialize refresh and cookie-changing actions across tabs. Broadcast
  and storage events contain only invalidation signals; cookies remain HttpOnly and access
  tokens remain in memory. Epoch/generation fences stop old responses. Automatic refresh
  must match subject, selected tenant and login session before retrying a request. Reconcile
  an interrupted cookie action after releasing the lock; never replay the original mutation.
  Without Web Locks, single-use server rotation remains authoritative; competing unsupported
  tabs may need sign-in. No non-atomic localStorage lock is presented as equivalent.
- No migration. Authored backend/frontend/Redis/browser tests are unexecuted under the user's
  two-phase testing policy. L15 closure and local completion await combined18+18A acceptance
  before19. Running Docker remains the verified Phase17 image/schema020. See phase18 report.

## ADR-043: Separate Scanner Dependency Availability from Version Attempts

- 2026-10-16: the supplied GitHub run38908641680/job116998545388 traceback timed out
  waiting for the first completed upload to become clean. Build, UI/API and storage checks
  passed. The traceback does not identify the remote updater/daemon/queue failure.
- Before claiming any version, the scan maintenance hint probes ClamD with the existing
  strict definition-freshness check, outside a DB transaction. Missing/stale scanner fails
  the maintenance execution visibly without spending a version attempt. Once available,
  normal claim/lease/process checks and three-attempt limits remain unchanged, including
  the per-scan freshness probe. A dependency can still fail after preflight; processing
  then retains its normal error/retry behavior. Never reset existing terminal errors silently.
- CI waits at most600seconds for the real operator scan health check (broker, storage,
  recent worker execution and fresh reachable scanner) before creating smoke uploads.
  Failure collects safe health/status and existing container logs. Do not weaken freshness,
  substitute a clean verdict or extend user upload deadlines to make CI pass.
- Outage/recovery and readiness timeout regressions are authored but unexecuted under the
  user's paired testing cadence. Exact remote root cause and a successful CI rerun remain
  pending; this is a startup/retry-budget correction, not proof that the remote outage is fixed.

## ADR-044: Retained-Reference Quota Admission and Bounded Provider Evidence

- 2026-10-16–17: serialize new source/replacement/preview admission with the existing
  tenant write lock. Aggregate retained bucket/file/object identities rather than maintaining
  a crash-sensitive counter or counting visible files. Current File/snapshot/initialization
  mirrors count once; history/trash/quarantine remain allocated until cleanup proof.
- StorageQuota is a separate per-workspace policy table, not an authentication Tenant field.
  Default Free10GiB/Team100GiB limits are configurable and operator-assigned, not paid billing.
  A confirmed DB-operator command changes plan/override; no customer entitlement endpoint.
  Lower limits preserve data, existing grants/reserved completions, downloads and cleanup;
  new admissions fail while over quota. Billing/AI gates remain25A/21 before enablement.
- Commit multipart initialization size before provider creation. Unknown legacy bounds pause
  new admissions, never count as zero. Queued previews retain their full1MiB output allocation
  until confirmed delayed cleanup, including failed/cancelled/unsupported work: an earlier
  provider write may have succeeded despite lost acknowledgement. No premature capacity return.
- Add a seventh rotating storage stage: bounded per-workspace object/multipart inventory plus
  exact rechecks of retained observations. Persist selection/failure before provider I/O and
  serialize evidence with admission. Inventory never deletes. Unknown/excessive manifests,
  namespace changes and failed/versioned-provider checks pause new allocations. Exact
  observed bytes can increase known allocation; no page absence is reclamation proof.
- Real local MinIO testing showed directory-prefixed multipart listing omitted an active
  upload while bucket/exact-key listings exposed it. Use bounded privileged bucket pages
  for multipart discovery, then tenant-filter before recording; object pages remain scoped.
  At most2 simultaneous upload IDs/1024 parts each are examined per key. Unknown larger
  populations require reconciliation. This is eventually observed evidence, not a snapshot
  or invoice-grade physical-byte claim. L41 assigns AWS/failure26, abuse27, alerts28,
  measured query/lock/inventory fairness32 and billing metering25A.
- Migration021 preserves legacy unknowns, adds no content bytes and does not delete resources.
  Rollback refuses custom policy, unknown/positive provider evidence and unmaterialized bounds
  the older schema cannot reconstruct. Normal source refs remain reconstructable; earlier
  quarantine/version/trash rollback guards remain unchanged. Restore a coordinated backup
  when representation would be lost. No production migration or provider certification.
- User explicitly moved19 ahead of18A; combined18+19 testing runs now, and18A remains pending.
  Phase19 report records initial failures and exact reruns rather than labelling the initial
  full suite green. No remote push/CI dispatch is authorized by implementation.


## ADR-045 � Current-tree sharing, recipient proof, ownership and directory groups (2026-10-17)

Phase18A extends read capabilities to a current folder subtree; every request rechecks the
publisher's live membership, resource management, ancestor/local ACL and scan release. Named
recipient links additionally require a live verified matching-email account session, explicitly
submitted by the recipient UI. They grant no workspace membership or external write capability.
Creation retry uses publisher-scoped UUID plus client-held random256-bit secret and immutable
options/password checks. Only hashes/fingerprint are persisted. Replays never renew expiry or
revive revocation; legacy clients without the pair retain their documented old semantics.

Management ownership is a separate override table, falling back to immutable created_by for
legacy resources. Transfer is local and serialized, checks target membership/ancestor access,
preserves upload/version provenance and explicit grants, and revokes affected links. Managers
retain recovery authority after departure; original upload control remains creator-scoped.

User explicitly included groups now. Workspace managers control membership; resource managers
assign existing local viewer/editor roles. Direct/group grants combine without deny precedence,
ancestor bypass, inherited editing or admin/ownership escalation. Departure clears memberships.
Group mutations invalidate affected link roots/subtrees in the same tenant transaction. Bounds
are100 groups/workspace,1000 members and100 resource grants/group; no measured-scale claim.
User explicitly resolved P02/P03 on2026-10-17: controlled external uploads/editing in dedicated24A after24/before25, and bounded scanned avatars in22A. Both automatically require implementation/acceptance at their checkpoint; neither is current functionality. Anonymous sharing stays read-only.
Acceptance is pending18A+20; migration022 is unapplied. Independent review/load/alert gates L42
are automatically due26/27/28/32. These are design/source decisions, not verification evidence.
