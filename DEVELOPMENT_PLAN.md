# Development Plan

This plan follows the master roadmap supplied by the project owner, with approved extensions for account lifecycle, multi-organization membership, and billing. Original Phase 0–33 numbers are preserved; added stages use letter suffixes. Complete, test, document, and explain each phase before starting the next. No AstraTransfer dependency is permitted.

Current state: Phase 17 is implemented and locally verified on application schema 020_malware_scanning. Real ClamAV/queue/provider release and detection, quarantine/browser tests, migration and app rescans pass; 113 frontend tests and 22/22 browser regression journeys pass. Exact backend baseline/focused reruns and the host FFmpeg skip are recorded in docs/phases/phase17.md. Phases 15/16 are committed in 6bf868f; Phase17 is committed with its verification notes. No browser deferral remains. AWS/production certification retains 26/31 and other assigned gates.

Next action when requested: Phase 18 realtime and its due limitations. Phase18 has not started. Keep production-provider, security, quota, monitoring and recovery gates assigned to their later phases.

## Limitations ownership and closure

Every numbered/lettered phase report must include "Limitations requiring explicit work": inherited/new IDs, concrete missing behavior/impact, required implementation or verification, assigned checkpoint, acceptance checks and status/evidence. Update docs/LIMITATIONS_BACKLOG.md, this roadmap and CONTINUE.md together; if no new gaps are identified, state that and retain the inherited open-item review. The report requirements are in docs/phases/README.md.

Standing user instruction: an ordinary "continue" authorizes the next scheduled development step, including its assigned limitation fixes and acceptance checks. Read docs/LIMITATIONS_BACKLOG.md before implementation, include every due L item and P decision in the working scope, and do not wait for the user to request each limitation separately. Complete the authorized implementation, tests and documentation autonomously. New limitations must receive an ID, checkpoint and acceptance criteria rather than being silently deferred.

Do not mark a phase complete or advance past it with an unresolved assigned acceptance check. Complete independent work when an external dependency is unavailable, keep the affected item explicitly open, and report the exact dependency and next action. Ask only for genuinely missing product decisions, credentials, externally controlled prerequisites or actions requiring separate authorization; an existing agreed scope is not a reason to ask again. Deliberate D constraints are reviewed/documented, not falsely promised to disappear. This instruction governs active development when work resumes; it does not create background/scheduled execution or authorize remote push, external CI dispatch, publication, paid resources or destructive data removal.

[Limitations backlog and schedule](docs/LIMITATIONS_BACKLOG.md) is the current register of historical gaps, resolved items, planned closures, product decisions and intentional constraints. Entries now extend through L38; closed local scope, open verification, product decisions and design boundaries are labelled individually. Historical phase reports remain records of their original scope, not the live backlog.

Every phase must reference the relevant register IDs and record actual acceptance evidence. Scheduling does not close an item. Security/data-loss defects block further work immediately. Remote CI requires separate push/dispatch authorization; production readiness is not inferred from completed phase numbers. Phase order is a dependency schedule, not a calendar-date or duration promise.

## Immediate Verification Gate — Existing Infrastructure

Status: Local PostgreSQL/migration/Docker verification passed. Remote CI run remains pending; this is verification work, not a future feature phase.

- Obtain a successful CI run for PostgreSQL-backed API/concurrency tests, real migrations, and Docker smoke checks before describing infrastructure behavior as verified. Do not defer this to Phase 30.
- Verify migration upgrade, schema alignment, downgrade/re-upgrade, and existing-data preservation on PostgreSQL.
- Verify frontend loading, API proxying, registration/session flow, and membership onboarding against the running container stack; extend the smoke job where necessary.
- Record the tested commit and CI run reference in CONTINUE.md. Fix failures rather than substituting SQLite results or marking an unexecuted check as passed.
- A push or external CI dispatch still requires explicit user authorization. No push is authorized by this roadmap update.

## PHASE 0 — Project Foundation

Status: Implemented; local Docker/PostgreSQL integration verification passed. Remote CI pending.

- repository setup
- project documentation
- frontend skeleton
- FastAPI skeleton
- PostgreSQL
- Docker development environment
- configuration
- health checks
- Git setup
- initial CI

## PHASE 1 — Authentication

Status: Implemented; local Docker/PostgreSQL integration verification passed. Remote CI pending.

- registration
- login
- password hashing
- authentication
- logout
- protected routes
- basic security

## PHASE 2 — Users + Organizations

Status: Implementation complete; local Docker/PostgreSQL runtime verification passed. Remote CI pending.

- user profiles
- organizations
- membership
- basic roles
- tenant isolation foundation

Implemented scope: full-name profiles, organizations using existing tenants, explicit memberships, owner/admin/member management, member removal, and private invitations for new accounts. Phase 2B extends this to multiple organizations and verified existing accounts; granular resource permissions belong to Phase 12.

## PHASE 2A — Email, Account Recovery + Session Lifecycle

Status: Implemented and locally verified, including real-browser/SMTP journeys and PostgreSQL/Docker checks. Remote CI and production provider verification remain pending.

Account lifecycle scope: verified users can delete profile/access after transferring ownership in every organization through Phase 2B. Production email transport requires operator configuration; SMTP is at-least-once under ambiguous acknowledgement, while account actions remain single-use.

Dependencies: Phase 2. Implement before multi-organization onboarding and public customer use.

- Real invitation and transactional email delivery through a configured transport; use a local SMTP inbox for development, not fake delivery-success responses.
- Email verification with expiring, purpose-bound, single-use tokens; verify ownership before binding invited existing accounts or granting verified-email privileges.
- Password reset with single-use tokens, safe expiry, enumeration-resistant responses, and revocation of affected sessions.
- Email changes requiring recent authentication, verification of the new address, uniqueness checks, and notification to the previous address.
- Session listing, individual session revocation, and sign-out of all devices, with defined access-token invalidation behavior.
- Account deletion with explicit confirmation, a documented retention/deletion policy, and protection against abandoning an organization as its sole owner. Complete organization-aware handling alongside Phase 2B.
- Rate limits for login, recovery, verification, resend, and invitation flows; retries for transient email delivery failures without duplicate side effects.

Completion criteria:
- Demonstrate real delivery to the local inbox and the complete verification/reset/email-change browser journeys.
- Expired, replayed, wrong-purpose, wrong-account, and replaced tokens are rejected. Secrets/passwords do not enter logs.
- Recovery does not disclose account existence; password reset and session revocation reject credentials according to the documented invalidation policy.
- Unverified callers cannot claim another person's invited account or change email without proof of ownership.
- Delivery failure is visible/retryable; no verification state changes merely because an email was queued.
- Add backend, database, and critical browser tests; document deployment transport requirements and remaining provider verification limits.

## PHASE 2B — Multiple Organizations + Membership Lifecycle

Status: Implemented and locally verified on 2026-10-14. PostgreSQL concurrency/migrations, browser journeys and rebuilt Docker runtime pass. See docs/phases/phase2b.md. Remote CI pending.

Dependencies: Phase 2A. Complete before Phase 3 so file/folder schemas do not depend on the temporary single-organization user model.

- Separate global user identity from organization membership; migrate existing users/memberships without losing account access.
- Allow verified existing users to accept invitations into additional organizations, without silently moving accounts or inheriting unrelated privileges.
- Organization listing/creation and explicit workspace switching; derive the active tenant and role from an authorized membership.
- Bind sessions/refresh behavior to an explicit tenant-selection policy. Recheck membership on protected requests and isolate caches during switching.
- Transactional ownership transfer to an eligible active member with recent authentication and owner confirmation. Prevent an organization from losing its final owner under concurrent requests.
- Owner-authorized re-invitation/reactivation of removed members after identity verification, with an explicitly assigned role. Do not restore access through an old invitation or revoked session.
- Remove membership within one organization without disabling the user's access to other organizations; revoke affected organization access and handle active-workspace removal safely.
- Complete account-deletion behavior across memberships and require ownership transfer before deleting a sole owner's account.

Completion criteria:
- One user can belong to two organizations with different roles and switch without cross-tenant data, token, or query-cache leakage.
- Unrelated users cannot list/switch into another organization; stale JWT roles and removed memberships cannot restore privileges.
- Ownership transfer is atomic; concurrent removal/demotion/transfer cannot produce an ownerless organization or an unauthorized owner.
- Reactivation requires current owner authorization and verified identity; old credentials remain revoked.
- Removing one membership leaves other authorized memberships usable. Existing-account migration preserves emails, password hashes, and documented session behavior.
- Add PostgreSQL migration/concurrency tests and browser journeys for invitation acceptance, switching, removal, ownership transfer, and account deletion.

## PHASE 3 — Folder System

Status: Implemented and locally verified on 2026-10-14. Folder hierarchy, mutation permissions, concurrent moves, tenant constraints, migrations, Chromium and Docker folder checks pass. See docs/phases/phase3.md. Remote CI pending.

- create folder
- rename
- move
- hierarchy
- folder permissions foundation

Implemented policy: verified active members read workspace folders and create at root; folder creators/owners/admins modify folders and create within writable parents. Phase 12 now adds private/shared viewer/editor ACLs and mandatory ancestor read gates. Names are normalized and case-insensitively unique per parent. Maximum depth is 64. Phase 13 now adds completed-content trash/restore with retained ACLs.

## PHASE 4 — File Metadata

Status: Implemented and locally verified on 2026-10-14. See docs/phases/phase4.md. Tenant-scoped pending records, folder relationships, provenance, indexes, listing/detail APIs and UI pass SQLite/PostgreSQL, migration and browser checks. Phase 4 established pending declarations only; Phase 6 now adds public upload reservations and verified uploaded state. Downloads remain Phase 7. Remote CI pending.

- file model
- metadata
- file/folder relationships
- indexes
- ownership

## PHASE 5 — Object Storage

Status: Implemented and locally verified on 2026-10-14. See docs/phases/phase5.md. Private local bucket, tenant-scoped S3 adapter/UUID keys, bounded internal object operations, safe errors and real disposable-bucket tests pass. Phase 5 established the internal adapter; Phase 6 now connects public uploads and persisted object references, while downloads remain Phase 7. Phase 5 required no migration. Remote CI and production-provider verification pending.

- MinIO
- S3 abstraction
- bucket configuration
- storage keys
- basic object operations

## PHASE 6 — Basic Upload

Status: Implemented and locally verified on 2026-10-14. See docs/phases/phase6.md. Creator/workspace/parent-authorized reservations, signed size/checksum/conditional direct PUT, completion verification, retry/reconciliation and browser upload UI pass database/provider/browser/Docker checks. Default cap 100 MiB, grant 15 minutes, completion grace 5 minutes. Uploaded does not mean scanned; downloads remain Phase 7, multipart/resume/abandoned cleanup Phases 8/9. Remote CI/production provider checks pending.

- upload flow
- presigned uploads
- metadata persistence
- validation
- upload completion

## PHASE 7 — Basic Download

Status: Implemented and locally verified on 2026-10-14. See docs/phases/phase7.md. Authorized provider-checked attachment downloads pass database/provider/browser/Docker checks. Phase 7 introduced no migration. Remote CI and production provider checks remain pending.

- permission checks
- signed URLs
- secure downloads
- download metadata

## PHASE 8 — Chunked/Multipart Uploads

Status: Implemented and locally verified on 2026-10-14. See docs/phases/phase8.md. 197 backend tests on SQLite/PostgreSQL with real MinIO, 49 frontend tests, 14 Chromium journeys and rebuilt Docker SMTP/basic/multipart upload/download smoke pass. Schema is 008_multipart. Remote CI and production provider checks remain pending.

- multipart upload
- chunk management
- part tracking
- failure handling

Scope: bounded chunk hashing/direct transfer, signed per-part size/SHA-256, server-verified provider receipts, composite checksum completion, same-form retries and explicit cancellation. Default maximum 1 GiB with 8 MiB parts and a one-hour session. Reload-based resume and automated abandoned-upload cleanup remain Phase 9.

## PHASE 9 — Resumable Uploads

Status: Implemented and locally verified on 2026-10-15. See docs/phases/phase9.md. 206 backend tests on SQLite/PostgreSQL with real MinIO, 53 frontend tests, 14 Chromium journeys and Docker SMTP/progress/resume/download/maintenance checks pass. Schema is 009_upload_cleanup. Remote CI and production verification remain pending.

- upload sessions
- persistent progress
- retry
- resume after interruption
- abandoned upload cleanup

Scope: creator-authorized progress discovery, original-manifest resume after reload, only missing-part transfer, unchanged deadlines, durable pre-provider initialization intents and automatic expired/abandoned cleanup. Cleanup waits for expiry, grace and settling delay; hidden tombstones release names but retain references for retries/late writes. The worker refuses versioned buckets until explicit version-aware cleanup exists. Production provider/lifecycle/maintenance-IAM verification remains required.

## PHASE 10 — File Search

Status: Implemented and locally verified on 2026-10-15. See docs/phases/phase10.md. 214 backend tests on SQLite/PostgreSQL with real storage, 60 frontend tests, 15 Chromium journeys and rebuilt Docker search/transfer/schema/maintenance checks pass. Synthetic PostgreSQL index paths are verified; production load/provider/remote CI checks remain pending.

- filename search
- filtering
- sorting
- pagination
- efficient indexes

## PHASE 11 — Sharing

Status: Implemented and locally verified on 2026-10-15. 225 backend tests on SQLite/PostgreSQL, 66 frontend tests, 16 Chromium journeys and rebuilt Docker sharing/transfer/schema/maintenance checks pass. See docs/phases/phase11.md. File-only external links, 1–720 hour expiry, optional passwords, metadata-only access, grant limits and revocation are implemented. Public capabilities preserve tenant-scoped object checks. Remote CI/production verification remain pending.

- share links
- expiry
- passwords where appropriate
- download restrictions

Scope: grant limits count issued URLs, not completed downloads. Existing signed URLs remain usable until their short expiry. Member removal/role updates/ownership transfer/account deletion revoke affected published links. Private recipient ACLs and folder sharing are not claimed.

## PHASE 12 — Permissions/RBAC

Status: Implemented and locally verified on 2026-10-15. 235 backend tests on SQLite/PostgreSQL, 72 frontend tests, 17 Chromium journeys and rebuilt Docker transfer/sharing/ACL/schema/maintenance checks pass. See docs/phases/phase12.md. Workspace/private visibility, explicit viewer/editor grants, ancestor read gates, filtered search/list pages, guarded transfer/publishing and permission controls are implemented.

- viewer
- editor
- owner/admin roles
- resource-level authorization
- secure access checks

Resource read ACLs now apply before search/list pagination and folder-name context. Viewers read/download; editors rename resources and create content in editable folders; creators/managers control ACLs, moves and publication. Grants are resource-local, every private ancestor must be accessible, and permission changes revoke affected external links. Existing content defaults to workspace visibility.

## PHASE 13 — Trash + Restore

Status: Implemented and locally verified on 2026-10-15. 250 backend tests on SQLite/PostgreSQL, 77 frontend tests, 18 Chromium journeys, actual byte-reclamation/migration checks and rebuilt Docker trash/restore/queue/schema/maintenance checks pass. See docs/phases/phase13.md. Completed-file/folder batch trash, 30-day retention, ACL-scoped pages, original-location restore/conflicts, explicit purge confirmation and durable provider cleanup are implemented.

- soft delete
- trash
- restore
- permanent delete
- cleanup jobs

Trash retains exact object references and ACLs. Restore preserves independently trashed children and rejects active name conflicts. Permanent folder deletion includes nested trash and commits irreversible intent before provider operations. Cleanup waits past upload authorizations, confirms absence, retries retained tombstones and fails closed on versioned/suspended buckets. Pending uploads must finish or clean before containing-folder trash. SQL backups cannot restore purged bytes. Phase 14 now includes every application snapshot/pending candidate in retention/purge. Provider bucket versioning remains disabled and needs explicit VersionId lifecycle verification before enablement.

## PHASE 14 — File Versioning

Status: Implemented; local SQLite/PostgreSQL, browser and rebuilt Docker verification passed (2026-10-15). See docs/phases/phase14.md.

- versions
- current version
- restore version
- metadata/history

Immutable application versions use distinct object keys on an unversioned bucket. Existing basic/multipart objects are version 1; replacement uploads use the basic cap (default 100 MiB), with multipart replacement/reload resume deferred. Current-version changes use a monotonically increasing generation; restore preserves logical name/location/ACL and revokes external links. History is reader-accessible. Retained/pending bytes are reported separately, without aggregate quota enforcement. Trash/expired-candidate cleanup preserves all exact references. See ADR-031. Coordinate any future retained application versions with trash purge and quota calculation. Before enabling provider bucket versioning, extend and verify upload/trash cleanup with explicit version handling. Delete markers alone do not establish byte reclamation; current Phase 9 maintenance fails closed on versioned buckets.

## PHASE 14A — Version Transfers, Resume/Cancel and Pruning

Status: Implemented and locally verified 2026-10-15; committed as 98a4a70. L02/L03 and L04 core lifecycle acceptance pass. Evidence: docs/phases/phase14a.md. L04 aggregate quota/audit retention remain assigned to 19/20; external production/remote CI gates remain open.

Closure ownership: L02–L04 (L04 accounting/audit integration continues in 19/20).

- Multipart replacement candidates with bounded hashing, provider receipts/composite verification and unchanged logical-file identity/current content until verified activation.
- Secret-free reload-resume manifests, original-file validation, missing-part progress, original deadlines and explicit cancellation/reconciliation.
- Configurable version pruning/individual history deletion with clear authority, protected current content, durable deletion intent and exact-reference retries.
- Preserve ACL/ancestor boundaries, generation conflict handling, share revocation and all-version trash/accounting behavior.

Completion criteria:
- Actual basic/multipart replacement bytes, empty files, lost acknowledgements, reload, changed input, workspace/permission changes and concurrent restore/abort/complete/prune cases pass.
- Current or in-flight content cannot be pruned accidentally; expiry/grace/settle and confirmed provider absence govern cleanup. Retained accounting changes only after verified reclamation.
- SQLite/PostgreSQL migration/data preservation, provider integration, frontend/browser and rebuilt Docker checks are recorded. Provider bucket versioning remains disabled unless its separate verified lifecycle decision is implemented.

## PHASE 14B — Core Library Movement and Recovery

Status: Implemented and locally verified 2026-10-15; included in this handoff commit. L05–L08 close for the documented tracked-record scope. See docs/phases/phase14b.md for database/provider/browser/Docker evidence and L37 follow-up in 16/26.

Closure ownership: L05–L08.

- Completed-file moves with source/destination/ancestor authority, conflict handling, share revocation and immutable version keys.
- Explicit destination/name selection for trash recovery while preserving ACLs, batch boundaries and original identities.
- Safe cancel-transfers-then-trash flow for folders containing pending transfers; retain the current protective block until this workflow is implemented.
- Authorized remediation/discard of legacy metadata with no upload reference, without inventing bytes or losing cleanup records.

Completion criteria:
- Cross-tenant/private-parent/name conflicts, missing parents, mixed creators, old independent trash, concurrent moves/restores/cancellations and rollback/data preservation are tested.
- No action weakens authorization or bypasses original provider deadlines, durable cleanup references or current-version safety. Record actual backend/provider/browser/Docker evidence.

## PHASE 15 — File Preview

Limitations closure work: L09: bounded safe preview/detected-type handling with tenant/version-aware derived output; scan integration follows in 17. Current derivatives are transient. L38 tracks bounded video/queued-preview lifecycle in 16/26; source/pixel/page/timeout limits remain explicit.

Status: Implemented and locally verified; deferred work resumed/completed 2026-10-16. Full Chromium passes 22/22, frontend passes 105 tests/lint/build, and disposable cleanup is complete. Shared-cache refresh after navigation was fixed and regression-tested. Earlier 306 backend and native/live smoke evidence remains valid; this completion changes frontend behavior only. See docs/phases/phase15.md.

- images
- PDFs
- text
- safe supported previews
- video support where appropriate

## PHASE 16 — Redis + Background Jobs

Completed locally 2026-10-16: maintenance leases/stages/health, L37 reconciliation and L38 queued previews/static posters. Actual decoder/isolation, broker restart, prefork crash/real-clock lease recovery, two-tenant bounded cleanup, PG migrations/provider lost-ACK/late-write/versioning refusal and the Phase16-only browser journey pass. Source/application head 019. AWS certification remains 26/31. Phase 15's separate final browser checks subsequently passed. See docs/phases/phase16.md for exact results and initial failures resolved by reruns.

Limitations closure work: L20/L22/L23/L25/L37/L38 and P04 provider decision: reliable jobs/inventory cursors and exact-reference lifecycle, safe operator reconciliation for contradictory legacy metadata/intents, bounded isolated video/poster jobs and version-aware queued previews/retries/invalidation, choose maintained production storage before integration certification, decide/enforce unversioned versus fully version-aware provider policy, and define job/backlog health. Verify preview decoder limits, cancellation and live ACL/prune/trash races; retain unsupported fallback. Never enable bucket versioning without verified cleanup for every path.

Status: Implemented and locally verified. AWS deployment/security/load extensions retain their assigned checkpoints.

- Redis
- Celery
- job architecture
- task retries
- worker monitoring

## PHASE 17 — Virus/Malware Scanning

Limitations closure work: L09: quarantine, verified release and malicious/oversized content failure handling; uploaded is not synonymous with safe.

Status: Implemented and locally verified. Exact-version quarantine/release, private ClamAV, durable scan queue, retries/health, migration, real-provider/queue/browser checks and application upgrade pass. See docs/phases/phase17.md, ADR-041 and L39 for explicit production extensions.

- asynchronous scanning
- quarantine
- safe release workflow

## PHASE 18 — Realtime

Limitations closure work: L15: cross-tab workspace/refresh coordination, scoped-cache reset and roster/ACL/reconnect events; verify refresh security again in 27.

Status: Not started.

- WebSockets
- upload/processing events
- notifications
- reconnect handling

## PHASE 18A — Collaboration Completion and Explicit MVP Scope

Status: Planned; not implemented. Complete after 18 and before 19.

Closure ownership: L10–L14. Scope decisions: P01–P03.

- Folder read-sharing with explicit subtree/current-ancestor behavior and move/revocation tests.
- A distinct named-recipient identity-proof flow; anonymous/password capability links keep their documented forwarding semantics.
- Idempotent share creation without exposing stored raw secrets or misrepresenting URL grants as completed delivery.
- Authorized resource ownership transfer with membership, version provenance, grant/link and ancestor consequences.
- Tenant-scoped member/grant lookup and readable recipient selection beyond the currently loaded page.
- Decide whether groups/custom roles, external editing/upload and profile avatars belong in the MVP. Record include/exclude decisions; included features require their own implementation and acceptance evidence before support is claimed.

Completion criteria:
- Sharing/ownership/group scope cannot bypass private ancestors, tenant membership or current permissions, including concurrent move/removal/restore operations.
- Actual recipient proof, lost-response replay, revoked access and relevant desktop/mobile journeys pass. Complete P01–P03 decisions explicitly rather than leaving them as indefinite future work.

## PHASE 19 — Storage Quotas

Limitations closure work: L19 and L04 accounting: concurrent reservations, retained/current/history/trash/pending accounting, orphan reconciliation and safe over-quota behavior. Introduce bounded AI budgets before AI enablement; integrate subscription entitlements in 25A.

L39: explicitly count retained quarantined/blocked/oversized content and scan reservations; test retries/cleanup without double counting or silently exempting bytes.

Status: Not started.

- usage calculation
- quotas
- enforcement
- plan-specific limits

## PHASE 20 — Audit Logs

Limitations closure work: L21/L32/L36 and L04 retention: audited content/permission/deletion transitions, technical metadata retention/compaction that preserves live cleanup refs, and honest issued-grant events rather than completed-download claims.

Status: Not started.

- user actions
- security-sensitive events
- organization-level audit history

## PHASE 21 — AI Document Processing

Limitations closure work: L16 tags/L17 content processing and L19 bounded AI cost limits; enforce source/version ACL and invalidation boundaries on every derived artifact.

Status: Not started.

- document extraction
- metadata generation
- automatic tagging
- summarization

## PHASE 22 — Semantic Search

Limitations closure work: L17: current-authority retrieval, version/deletion invalidation and actual semantic-index behavior; lexical/navigation gaps close in 22A.

Status: Not started.

- chunking
- embeddings
- pgvector
- semantic retrieval

## PHASE 22A — Search, Navigation and Large-List Pagination

Status: Planned; not implemented. Complete after 22 and before 23.

Closure ownership: L16/L18; measured scale verification continues in 32.

- Define recursive filename scope, fuzzy/accent normalization and tag filtering separately from semantic search.
- Use a common cursor/keyset strategy where needed for files/search/history/large membership lists; add scoped totals only where useful.
- Preserve current tenant/resource/ancestor predicates before pagination/count/context and document concurrent-update consistency.

Completion criteria:
- Private deep hierarchies, broad/short terms, Unicode, concurrent changes and large-list navigation are tested with actual query-plan evidence.
- Do not promise unlimited pages or immutable snapshots; production latency/throughput claims require Phase 32 measurements.

## PHASE 23 — Ask My Files / RAG

Limitations closure work: L17: permission-aware source chunks/citations, current-version/deletion semantics and prompt-injection bounds.

Status: Not started.

- retrieval
- context construction
- LLM
- citations/source references
- permission-aware retrieval

## PHASE 24 — Public API

Status: Not started.

- API versioning
- API keys/tokens
- rate limits
- documentation

## PHASE 25 — Webhooks

Status: Not started.

- webhook subscriptions
- event delivery
- retries
- signatures
- idempotency

## PHASE 25A — Billing, Subscriptions + Entitlements

Limitations closure work: L19: integrate verified plan entitlements, storage/AI metering and safe downgrade/over-quota reconciliation; payment infrastructure remains a separate production prerequisite.

Status: Not started.

Dependencies: Phase 19 quotas, Phase 20 audit logs, and Phase 25 webhook reliability. Implement before paid customer launch; billing is not required for an earlier unpaid resume demo.

- Integrate a payment provider in its real test environment; add checkout and a billing-management flow without storing card details in CloudVault.
- Model organization subscriptions, server-side plan entitlements, storage/API limits, and AI usage budgets.
- Verify webhook signatures; process duplicate and out-of-order events safely. Reconcile local subscription state against provider state.
- Support plan changes, renewal, cancellation, failed payments, grace periods, and recovery, with documented access behavior.
- Enforce quotas/entitlements on the backend. Frontend claims, checkout redirects, or unverified webhook payloads cannot grant paid features.
- Define downgrade/over-quota behavior that preserves existing customer files; handle usage metering and concurrent limit enforcement.
- Tenant-scope billing administration and audit sensitive changes. Bound AI consumption and track provider costs without logging document secrets.

Completion criteria:
- Demonstrate subscription purchase/change/cancellation and failed-payment recovery using actual provider test-mode events.
- Invalid signatures, replayed events, out-of-order events, forged frontend payment claims, and cross-tenant billing requests cannot grant unauthorized entitlements.
- Duplicate events produce one effective transition; reconciliation recovers missed events and interrupted processing.
- Downgrades and failed payments follow documented rules without silently deleting files; concurrent requests cannot bypass plan limits.
- Add integration/security tests and deployment configuration; production payment credentials remain an explicit deployment prerequisite.

## PHASE 26 — Testing Hardening

Limitations closure work: L20/L22/L23/L31/L33/L35: actual chosen-provider/browser/outage/replay matrix, real-clock lifecycle evidence, initial query/lock profiling/timeouts, migration failures and paired DB/object recovery tests.

L39: verify actual AWS scan streams, immutable conditional reads, scanner image pinning/private deployment and failure/recovery, including outstanding pre-upgrade capabilities.

Status: Not started.

- unit tests
- integration tests
- E2E
- security tests
- recovery tests

Completion criteria:
- Critical browser journeys cover account recovery, multi-workspace switching, uploads/resume/downloads, sharing, membership changes, and billing where enabled.
- Run integration tests on real PostgreSQL, object storage, Redis, and workers; cover outages, replay, retries, concurrency, and database/object-storage consistency.
- Record repeatable test commands and actual results; mocks alone do not establish external-service correctness.

## PHASE 27 — Security Hardening

Limitations closure work: L15/L21/L24/L27–L30/L32 and P04 delivery decision: MFA/recovery codes and inaccessible-mailbox support policy, refresh-family replay handling, trusted proxies/rate/CPU/timing abuse review, provider/retention/logging policies and independent assessment requirements before public release.

L39: review scan-size/format/encrypted/archive policy, false negatives and parser isolation; implement/verify the selected retroactive rescan, signature-change threat-response and released-content revocation policy.

Status: Not started.

- authentication review
- authorization review
- SSRF protection
- IDOR review
- upload security
- secrets
- rate limiting

Completion criteria:
- Review account lifecycle, workspace switching, ownership transfer, billing authorization, and file access against a documented threat model and applicable OWASP ASVS controls.
- Test malicious uploads and AI prompt injection, including permission enforcement before retrieval and cross-tenant disclosure attempts.
- Resolve release-blocking findings, document remaining risks, and verify authentication/authorization/rate limits at every externally exposed boundary.

## PHASE 28 — Observability

Limitations closure work: L25/L26/L32/L36: feature-aware dependency probes, cleanup/backlog age/errors, real SMTP alerts, secret-safe logs/traces/metrics and clearly labeled provider-observed download telemetry.

L39: alert on signature freshness/updater failure, unavailable scanner, oldest pending/failed scan and quarantine counts; verify alerts on actual failures and recovery.

Status: Not started.

- structured logging
- OpenTelemetry
- metrics
- tracing
- Prometheus
- Grafana

## PHASE 29 — Docker Productionization

Limitations closure work: L24/L34: production resource/image/configuration hardening and reproducible deployment setup; local WSL limits are not production capacity evidence.

Status: Not started.

- optimized images
- environment configuration
- production compose/deployment configuration

## PHASE 30 — CI/CD

Limitations closure work: L34: complete repeatable test/build/security/deploy automation. The already-pending successful remote run remains immediate L01 and is not postponed here.

Status: Not started.

- automated tests
- linting
- build
- security checks
- container build
- deployment pipeline

## PHASE 31 — Cloud Deployment

Limitations closure work: L20/L22–L26/L31/L34/L35: verify the actual maintained storage/SMTP providers, IAM/encryption/CORS/TLS/clock/credential/lifecycle settings, hosted services and paired backup configuration before exposing production traffic.

L39: deploy pinned maintained ClamAV/updater with private networking, protected signatures, production resource limits/monitoring and a coordinated quarantine rollout/recovery plan.

Status: Not started.

- production database
- Redis
- object storage
- backend deployment
- frontend deployment
- HTTPS
- domain
- secrets

## PHASE 32 — Load Testing

Limitations closure work: L18/L29/L33: measure representative tenant-lock, search/ACL/history, transfer, queue and abuse workloads; tune only from recorded results.

L39: measure scanner RAM/CPU, source-size/format limits, queue delay and tenant fairness using representative files; record supported production scan limits from results.

Status: Not started.

- concurrent users
- file workloads
- API workloads
- queue workloads
- bottleneck analysis

## PHASE 33 — Production Readiness

Limitations closure work: L21/L29/L30/L31/L33/L35: close release blockers, review all remaining L/P decisions, run timed paired DB/object restore drills, record recovery/availability/cost/retention targets and incident/rollback runbooks. Deliberate design constraints remain documented, not falsely marked fixed.

Status: Not started.

- backups
- recovery strategy
- cost controls
- abuse controls
- documentation
- monitoring
- operational runbooks
- final architecture review

Completion criteria:
- Successfully restore database metadata and stored file objects; record measured recovery time and recoverable data loss against explicitly chosen targets.
- Define availability/latency targets, actionable alerts, incident procedures, migration rollback strategy, retention/deletion rules, and tenant/AI cost limits.
- Confirm critical integration/E2E/security checks and representative load tests in the deployed environment; record configuration, workload, and actual measurements.
- Paid launch additionally requires Phase 25A verification and configured real email/payment transports. Phase completion alone is not evidence of production readiness.

---
