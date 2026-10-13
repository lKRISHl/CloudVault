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

## Responsible Disclosure Policy
Development MinIO binaries are built from pinned official source revisions with
upstream licenses preserved. The community repositories are archived and unmaintained;
production storage requires a maintained S3 provider/deployment review. A successful
development storage smoke check does not certify production security.

*(Placeholder: Details on how to report vulnerabilities will be added prior to production release.)*
