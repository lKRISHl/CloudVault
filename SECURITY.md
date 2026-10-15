# Security Considerations

## Phase 0 Baseline

- **CORS Configuration**: Restrict origins in production. Local development allows specific localhost ports.
- **Input Validation**: All incoming API requests must be validated using Pydantic models.
- **Secrets Management**: Development-only defaults exist in settings and Compose. Production startup rejects the default JWT signing secret and secrets shorter than 32 bytes. Supply a randomly generated key through secure environment configuration.

## Phase 1 Authentication
- **Passwords**: Argon2id hashes; login verifies a dummy hash when the email is unknown to reduce timing leaks.
- **Access tokens**: Short-lived JWTs (`sub`, `tid`, `role`) sent as `Authorization: Bearer`.
- **Refresh tokens**: Random secrets stored as SHA-256 hashes, rotated on refresh, revoked on logout, delivered in HttpOnly cookies.
- **Concurrent refresh**: An atomic conditional database update claims an unrevoked, unexpired token. Revocation and replacement are committed together. The frontend shares an in-flight refresh request within a browser tab.
- **JWT validation**: Signature, expiry, token type, required claims, active user status, and tenant ownership are checked.
- **Logout scope (Phase 2A)**: JWTs include a stable session ID. Every protected request checks the session's current database revocation/expiry state. Logout, password reset, email change, and session revocation reject subsequent requests using the affected access tokens and refresh cookies.
- **Tenant isolation**: Authenticated lookups require both `user_id` and `tenant_id` from the access token.

## Future Security Roadmap
- **RBAC (Role-Based Access Control)**: Granular permissions for files and folders.
- **Membership**: Global users have independent roles per organization. Richer resource permissions arrive in Phase 12.
- Rate limiting, token-family replay response, cross-tab refresh coordination, and wider security review remain future hardening work.

## Phase 2 Organizations
- Authenticated requests must have an active membership in the claimed tenant; roles are checked against current database state, not the JWT's role claim.
- Membership foreign keys enforce global user/organization references. Current membership and issuer authority are checked in services; request schemas reject owner grants and client-supplied tenant assignments. Session tenant and token tenant must match, even when a user belongs to both tenants.
- Cross-tenant member/invitation IDs return 404. Rosters and invitation lists are bounded and tenant-scoped.
- Only owners change roles or invite admins. Owners cannot be removed/demoted; admins cannot remove other admins. Removed members are disabled and their refresh tokens are revoked, so subsequent protected requests are denied.
- Invitation secrets are random, hashed at rest, expire after seven days, and are consumed atomically. Acceptance has transactional rollback and replay/concurrency coverage.
- A private invitation link grants pending account creation for its fixed email. Phase 2A sends a separate verification challenge and requires mailbox proof before organization access. Protect both links as bearer credentials.
- Invitation links use a URL fragment, which is not sent as part of the HTTP request URL. Do not add analytics or logs that record these secrets or request passwords.
- Role changes and removal invalidate invitations issued by the affected user. A replacement invitation invalidates earlier pending tokens for that organization/email.
- Existing accounts explicitly accept using the verified invited email. Removed memberships require a fresh owner-authorized reactivation invitation; old invitations/sessions never regain access. Rate limits apply to account/invitation/workspace creation/ownership actions; broader abuse controls remain future work.

## Phase 2B Workspace and Ownership Controls
- A session selects one workspace. Switching revokes its old access/refresh session and preserves the absolute expiry. Login without any membership permits account management but no organization access.
- Current-password reauthentication and literal TRANSFER confirmation protect ownership transfer. Tenant locks, conditional updates and a partial owner uniqueness index protect concurrent transfer/removal/demotion; normal routes cannot leave an organization ownerless.
- Removal revokes only the target organization membership/sessions. Global deletion checks ownership across all organizations before removing every membership and session.
- Frontend cancels and clears query state on switching, rejects stale responses and avoids retrying old workspace mutations through another tab's newly selected refresh cookie. Public verification remains independent of workspace changes.
- Migration preserves valid identity/session data and removed-member tombstones while retaining suspensions with intact memberships. Lossy downgrade is refused; restore a backup when data no longer fits the prior model.

## Phase 2A Account Lifecycle
- Organization routes require verified email; profile and recovery/session screens remain available to unverified accounts. Invitation possession alone does not verify an email address.
- Verification/reset/email-change links are random, hashed, purpose-bound, expire after 30 minutes by default, and are consumed atomically. Resending invalidates earlier links of the same purpose. Password reset invalidates outstanding account links and all sessions.
- Reset requests return the same status/message for eligible and unknown addresses and apply a minimum response duration; this is not a claim of perfectly constant timing under arbitrary database load.
- Email change requires verification of the current account address, a fresh password check, verification at the new address, and another fresh password check at confirmation. Account identity binding and uniqueness are rechecked; conflicts roll back without revoking valid sessions.
- Account endpoints enforce persistent atomic per-IP/per-account rate limits. Identity keys are HMAC-derived; untrusted forwarded IP headers are not accepted as client identity. Deployment must configure trusted proxy handling deliberately.
- Email bodies are encrypted in the outbox; SMTP exception text is not stored. Sent/expired/superseded payloads are purged. Delivery status exposes metadata only and does not claim mailbox delivery when SMTP has merely accepted a message.
- The dispatcher claims messages with a lease, retries bounded failures, and stops before action-link expiry. SMTP delivery is at-least-once under an ambiguous acknowledgement/crash; stable Message-ID and single-use account tokens prevent repeated account-state changes, but duplicate emails cannot be categorically ruled out.
- Production settings require HTTPS callback URLs, STARTTLS, and a non-default signing key. Configuration validation suppresses input values in errors to reduce accidental secret disclosure.
- Self-deletion requires verified email, current password, and literal confirmation. Owner deletion is blocked. Memberships, session access, recovery tokens, and pending personal payloads are removed/revoked; incoming invitation addresses and profile fields are redacted. Minimal pseudonymous IDs/timestamps remain for referential integrity; this is not a claim of legal compliance or total metadata erasure.
- The email maintenance job removes expired rate counters and obsolete token/session/invitation/outbox records according to the documented 30-day technical retention policy. Previously delivered messages in recipients' mailboxes cannot be recalled.
- PostgreSQL-backed backend tests and migration checks pass locally. MFA, cross-tab coordination, token-family replay response, independent security assessment, remote CI, and real production email-provider verification remain future/pending work.

## Phase 3 Folder Controls
- Folder parent/tenant composite foreign keys, sibling/root name uniqueness and self-parent checks enforce structural constraints. Every folder lookup is tenant-scoped; unrelated folder/parent UUIDs return 404. Client-supplied tenant/creator fields are rejected.
- Verified active members read shared workspace folders; creator or current owner/admin authority is required for writes, including destination/parent writes. Private/shared resource ACLs remain Phase 12 work.
- Structural writes lock before reading the graph, preventing concurrent moves from forming a cycle. Self/descendant moves, duplicate names and depth above 64 are rejected. Names reject path separators, dot-only paths and control/surrogate characters.
- UUID/tenant/user-scoped query state and Phase 2B stale-response protections isolate workspace changes. Queries do not retry client errors; transient/network failures receive bounded retries and folder views expose manual retry.
- Account deletion retains organization-owned folder metadata with a pseudonymous creator reference; deletion does not erase shared organizational content. Nonempty folder migration downgrade is refused; restore a pre-upgrade backup for rollback.

## Phase 4 File Metadata Controls
- File UUIDs and folder paths are tenant-scoped; foreign or missing resources return 404. Verified active membership is required even for read access. Internal creation rejects identity/status injection and requires parent write authority.
- Database composite foreign keys, sibling/root uniqueness, pending-state and nonnegative-size checks back service validation. Reservations use the tenant write lock, preventing name and parent-authority races with folder/organization changes.
- Size and MIME fields are explicitly declared/unverified. Pending metadata never grants download, preview, AI or scan clearance. Public creation and download URLs are absent until actual object validation exists.
- Creator deletion preserves organization-owned metadata and pseudonymous identity references. Populated downgrade is refused; use a pre-upgrade backup. Scoped query keys and existing session-generation checks guard stale workspace responses.

## Phase 5 Storage Controls
- Object keys contain validated tenant/file/object UUIDs, never filenames or client-provided paths. Every adapter operation rejects foreign tenant references before contacting the provider. Internal callers must still authorize membership/resource access through services.
- Local bucket provisioning disables anonymous access. Real tests deny anonymous GET/listing; Docker smoke checks application bucket listing denial. Production IAM/public-access controls need provider-specific review; local root credentials are development-only.
- Storage credentials are redacted, custom endpoints require complete credentials and a clean HTTP(S) origin, and production requires HTTPS/non-default local password. Native AWS credentials may use the SDK chain.
- Internal transfers are capped at 1 MiB. Writes conditionally reject replacement; reads check actual size/generation and reject oversized/truncated bodies. Streams close on failure/cancellation; SDK calls run outside the event loop. Errors do not expose raw provider messages.
- No public storage access is added. Presigned authorization, completion validation, CORS, scanning, lifecycle/cleanup and versioned deletion remain later work. Ambiguous acknowledgements and cancellation can leave completed writes that require reconciliation.

## Phase 6 Upload Controls
- Upload initiation derives creator/tenant/object identity server-side and requires verified membership plus parent write authority. Completion/reticketing is creator-only, tenant-scoped and rechecks current parent authority. Role demotion/removal cannot restore access through old JWT claims.
- Signed PUT binds object key, byte count, canonical SHA-256, generic content type and conditional creation. Actual provider HEAD size/checksum/type must match before uploaded state is committed; clients cannot submit verified completion facts. Database checks also reject incomplete/forged uploaded state.
- Separate public endpoint signing preserves Signature V4 host validity. Local CORS allows configured origins only; private bucket policy remains. Storage requests omit app cookies/Authorization and referrer. Grant responses use no-store; URLs remain temporary in-memory capabilities.
- Default cap 100 MiB, URL 15 minutes plus 5-minute completion grace and persistent grant/completion rate limits bound basic attempts. Uploaded files remain unscanned; no downloads/previews are added here. Declared MIME is never trusted as detected content type.
- Already issued capabilities cannot be immediately revoked by app logout/removal; provider writes may finish until expiry, while completion fails without current authority. Ambiguous acknowledgement/abort/expired pending data needs reconciliation and later abandoned cleanup. Production requires maintained provider checks, reviewed IAM/CORS/encryption and quotas/security controls.
- Migration 007 preserves metadata and refuses loss of upload references on downgrade; restore backups. Real tests use disposable databases/owned buckets, and the Windows browser harness has explicit validated bucket teardown. No destructive test points at application data.

## Responsible Disclosure Policy
Development MinIO binaries are built from pinned official source revisions with
upstream licenses preserved. The community repositories are archived and unmaintained;
production storage requires a maintained S3 provider/deployment review. A successful
development storage smoke check does not certify production security.

*(Placeholder: Details on how to report vulnerabilities will be added prior to production release.)*

## Phase 7 download boundary

Uploaded objects are offered through short-lived, no-store attachment GET capabilities after current membership, tenant metadata and provider HEAD integrity checks. Pending/missing/changed objects fail closed. Current shared-workspace read access includes members without write rights; private ACLs remain Phase 12. Generic octet-stream and attachment headers are presentation controls, not malware safety. URLs remain reusable until expiry and are not version-pinned; out-of-band replacement after HEAD remains a provider/versioning limitation. Native browser delivery does not establish completion telemetry. Do not persist/log signed URL values.

## Phase 8 multipart boundary

Multipart control remains creator-only with current verified membership and parent write authority; manager access cannot take over someone else's upload. Provider upload IDs/object references remain private. Signed part URLs bind number, size and SHA-256; confirmations inspect actual provider parts rather than trusting client receipts. Conditional completion and final HEAD verify declared integrity. Part grants/confirmations use separate persistent budgets (4096 per identity, 16384 per IP per configured rate window); initiation/completion/cancellation retain normal account limits.

Default limits are 1 GiB, 8 MiB parts, at most 1024 parts, and a one-hour upload deadline. Configuration allows up to 5 GiB and 5–32 MiB parts; the part-count bound still applies. Part grants last at most the configured basic URL duration or remaining session time, and never extend the session. Confirmation/completion allow the existing five-minute grace. Basic uploads retain their 100 MiB cap and full-buffer hashing; multipart hashing uses bounded chunks. These bounds are not aggregate quotas or malware scanning.

Part capabilities are reusable until expiry and may survive app permission revocation; completion checks current authority. Abort requests provider cancellation but cannot prove immediate cleanup of concurrent in-flight parts. Aborted/pending names remain reserved; automatic orphan cleanup and reload resume belong to Phase 9. Unknown provider-create acknowledgement can leave an untracked multipart upload; production must configure and verify provider abort-incomplete lifecycle rules. Composite checksums are explicitly identified, never represented as whole-file hashes. Production S3/R2 and browser compatibility remain deployment gates.

## Phase 9 resume and maintenance

Progress/resume recheck current creator, workspace and parent authority; provider inventory determines confirmed bytes. Original part checksums must match before new capabilities are issued. Reload resume requires the original file, occurs at part boundaries and never extends the deadline. No file handles, bytes or capabilities persist in browser storage. Fresh grants after expiry fail; completion retains the existing grace.

A durable initialization intent records the exact server-generated key, fingerprint and deadline before any provider create. It survives file-transaction rollback and account deletion so cleanup can find uploads despite ambiguous acknowledgements. These private records have an explicit retention purpose and are not a full-erasure claim. Name reclamation hides expired pending File tombstones after provider abort/delete and absence verification, retaining their references for repeated late-write sweeps. Completed/unexpired files are excluded; provider errors keep references and names for retry. Tests use disposable data; operator maintenance is separate from destructive test fixtures.

The cleanup worker needs reviewed maintenance credentials for bucket versioning inspection, multipart inventory/abort and object deletion. It must operate in an exclusive CloudVault namespace. Only canonical server UUID keys are considered by the supplementary orphan scan; unknown uploads wait beyond the maximum permitted session and grace. Local MinIO's broad-prefix inventory/cache has limitations, so current initialization recovery relies on durable exact-key intents. Legacy untracked keys lost from provider inventory require provider stale-upload lifecycle cleanup; production lifecycle is still a deployment gate.

Versioned/suspended buckets fail closed, since a delete marker does not prove reclamation. Before Phase 14 enables versioning, explicit version-aware cleanup must be verified. Local MinIO stale-upload expiry is configured at 24 hours with hourly scanning; the full-day timing has not been measured. A SQL backup cannot restore reclaimed object bytes; provider backups/restore require independent verification. Worker running state alone is not proof of successful cleanup; inspect maintenance results/errors and alerting remains a deployment requirement.

## Phase 10 search boundary

Current verified membership gates search. Tenant/non-cleaned constraints are unconditional; folder scope verifies the selected tenant's ancestor chain. Folder-name joins also match tenant identity. Creator filters never enumerate another tenant's accounts; foreign/nonexistent folders fail identically. Cleanup references/provider identities remain hidden. All current workspace members share read access; Phase 12 must apply private resource ACLs before search pagination/result context.

Filename terms normalize NFC/case folding and escape LIKE wildcard syntax, with bound parameters and whitelisted sorting. Queries reject control characters, unknown keys, incompatible scope/folder inputs, reversed sizes, offsets above 10000 and pages above 100. Separate persistent budgets are 1200 identity/4800 IP per configured window. These limits are not a production denial-of-service proof: broad/short terms, concurrent workloads, database statement timeouts and monitoring require deployment review. GET query values can enter access logs; configure appropriate logging/redaction/retention. Declared MIME/size remain untrusted for pending records and never imply scanning.

Client cache keys include workspace/user/filters/page; cancelled/stale workspace responses fail closed, and switching remounts search state. Responses are no-store. Result downloads still use the existing current-member/provider-checked attachment grant and inherit its capability/version/scan limitations.

## Sharing (Phase 11)
Only current verified file creators/workspace managers publish or manage completed-file links. All management lookups include tenant/file IDs. Anonymous access derives tenant scope from a random 256-bit capability hash; no caller-chosen tenant/key/provider is accepted. Optional passwords use Argon2 and are verified on each request. Public requests omit cookies/Authorization and disclose only filename, verified size, expiry and download availability after proof succeeds.

Tokens are returned once in URL fragments, consumed into browser memory and removed from the address/history; public POST bodies carry proof. No-store/no-referrer covers sharing errors and successes, with frontend referrer policy. Production HTTPS, proxy/IP trust and body logging/redaction review remain required. Persistent public limits are 100/IP and 100/capability per configured window (default 15 minutes); creation/revocation use ordinary account category budgets. Malformed validation errors precede service limits. Distributed/CPU abuse and provider/tenant-lock throughput require review.

Tenant serialization protects last-grant races and mutation ordering. Grant counters measure issued URLs, including ambiguous acknowledgement, not completed downloads. Published links revoke on member removal, role updates, ownership transfer and account deletion; current publisher authority is rechecked. Revocation cannot invalidate prior presigned URLs instantly or recall bytes. Files remain unscanned. Private ACLs, scans, quotas/audit and production hardening remain pending.
