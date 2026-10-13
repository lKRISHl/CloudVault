# Development Plan

This plan follows the master roadmap supplied by the project owner, with approved extensions for account lifecycle, multi-organization membership, and billing. Original Phase 0–33 numbers are preserved; added stages use letter suffixes. Complete, test, document, and explain each phase before starting the next. No AstraTransfer dependency is permitted.

Current state: Phase 2B implementation and local verification are complete: 92 backend tests, 24 frontend component tests, 9 Chromium journeys, PostgreSQL migrations/concurrency and the updated Docker stack. Evidence is recorded in CONTINUE.md; remote CI and production email-provider verification remain pending. Phase 3 has not started.

Next planned implementation: Phase 3, only on explicit user instruction. Phase 25A follows Phase 25 and precedes Phase 26.

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

Implemented scope: full-name profiles, organizations using existing tenants, explicit memberships, owner/admin/member management, member removal, and private invitations for new accounts. One organization per account remains the documented scope; granular resource permissions belong to Phase 12.

## PHASE 2A — Email, Account Recovery + Session Lifecycle

Status: Implemented and locally verified, including real-browser/SMTP journeys and PostgreSQL/Docker checks. Remote CI and production provider verification remain pending.

Current scope: one organization per account; verified non-owners can delete their profile/access, while owners are protected until Phase 2B ownership transfer. Production email transport requires operator configuration; SMTP is at-least-once under ambiguous acknowledgement, while account actions remain single-use.

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

Status: Not started.

- create folder
- rename
- move
- hierarchy
- folder permissions foundation

## PHASE 4 — File Metadata

Status: Not started.

- file model
- metadata
- file/folder relationships
- indexes
- ownership

## PHASE 5 — Object Storage

Status: Not started.

- MinIO
- S3 abstraction
- bucket configuration
- storage keys
- basic object operations

## PHASE 6 — Basic Upload

Status: Not started.

- upload flow
- presigned uploads
- metadata persistence
- validation
- upload completion

## PHASE 7 — Basic Download

Status: Not started.

- permission checks
- signed URLs
- secure downloads
- download metadata

## PHASE 8 — Chunked/Multipart Uploads

Status: Not started.

- multipart upload
- chunk management
- part tracking
- failure handling

## PHASE 9 — Resumable Uploads

Status: Not started.

- upload sessions
- persistent progress
- retry
- resume after interruption
- abandoned upload cleanup

## PHASE 10 — File Search

Status: Not started.

- filename search
- filtering
- sorting
- pagination
- efficient indexes

## PHASE 11 — Sharing

Status: Not started.

- share links
- expiry
- passwords where appropriate
- download restrictions

## PHASE 12 — Permissions/RBAC

Status: Not started.

- viewer
- editor
- owner/admin roles
- resource-level authorization
- secure access checks

## PHASE 13 — Trash + Restore

Status: Not started.

- soft delete
- trash
- restore
- permanent delete
- cleanup jobs

## PHASE 14 — File Versioning

Status: Not started.

- versions
- current version
- restore version
- metadata/history

## PHASE 15 — File Preview

Status: Not started.

- images
- PDFs
- text
- safe supported previews
- video support where appropriate

## PHASE 16 — Redis + Background Jobs

Status: Not started.

- Redis
- Celery
- job architecture
- task retries
- worker monitoring

## PHASE 17 — Virus/Malware Scanning

Status: Not started.

- asynchronous scanning
- quarantine
- safe release workflow

## PHASE 18 — Realtime

Status: Not started.

- WebSockets
- upload/processing events
- notifications
- reconnect handling

## PHASE 19 — Storage Quotas

Status: Not started.

- usage calculation
- quotas
- enforcement
- plan-specific limits

## PHASE 20 — Audit Logs

Status: Not started.

- user actions
- security-sensitive events
- organization-level audit history

## PHASE 21 — AI Document Processing

Status: Not started.

- document extraction
- metadata generation
- automatic tagging
- summarization

## PHASE 22 — Semantic Search

Status: Not started.

- chunking
- embeddings
- pgvector
- semantic retrieval

## PHASE 23 — Ask My Files / RAG

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

Status: Not started.

- structured logging
- OpenTelemetry
- metrics
- tracing
- Prometheus
- Grafana

## PHASE 29 — Docker Productionization

Status: Not started.

- optimized images
- environment configuration
- production compose/deployment configuration

## PHASE 30 — CI/CD

Status: Not started.

- automated tests
- linting
- build
- security checks
- container build
- deployment pipeline

## PHASE 31 — Cloud Deployment

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

Status: Not started.

- concurrent users
- file workloads
- API workloads
- queue workloads
- bottleneck analysis

## PHASE 33 — Production Readiness

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
