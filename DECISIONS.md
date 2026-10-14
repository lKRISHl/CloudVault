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
