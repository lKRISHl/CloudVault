# Phase 2A — Account Lifecycle and Email Delivery

Implemented and locally verified on 2026-10-13. Follow-up infrastructure verification passed: all 81 backend tests on PostgreSQL, full PostgreSQL migration cycle, complete Docker startup, HTTP/storage round trip, and registration email through the Compose dispatcher into Mailpit. Remote CI and real production email-provider verification remain pending. Phase 2B has not started.

## A. What we built

- Verification email on registration and invitation acceptance; organization features require verified email.
- Verification resend and generic password recovery, with expiring single-use links.
- Password reset followed by normal sign-in, with all prior sessions and account links invalidated.
- Email change with current-password checks, verification at the new address, old-address notifications, and complete session revocation.
- Active-session listing, individual revocation, logout, and sign-out of all devices. Revocation rejects access tokens as well as refresh cookies on subsequent requests.
- Verified non-owner deletion with explicit confirmation and profile redaction. Owners are protected until ownership transfer exists.
- Encrypted SMTP outbox, delivery status, bounded retry/deadline handling, Mailpit development setup, and technical retention maintenance.
- Persistent per-IP/per-account limits for account and invitation endpoints.
- Recovery/action/security screens and seven real-browser journeys using real loopback SMTP delivery.

## B. Why we built it

A password authenticates someone who knows it, but does not prove they own the email they entered. An invitation secret also does not independently prove mailbox ownership because the inviter receives that secret. A separate verification challenge closes that gap before organization access.

Users need a safe way to recover access and revoke unwanted sessions. A JWT signature alone cannot tell the server that a particular login was revoked after the token was issued. We now check a stable session record alongside the token.

Email delivery is a network operation that can fail. A durable outbox allows the request's account state to commit without pretending the message was already delivered.

## C. Architecture

```text
Browser account screens
       |
FastAPI routes / authentication and verified-email dependencies
       |
AccountService + AuthService + OrganizationService
       |
Database transaction
  |--> users / memberships / login_sessions / refresh_tokens
  |--> account_tokens: hashes and expiry
  |--> email_outbox: encrypted payload and delivery state
              |
       Dedicated email dispatcher
              |
          SMTP transport
              |
     Local inbox / configured production provider
```

Database state is shared across API/dispatcher instances. General background processing still belongs to Phase 16; this small dispatcher implements the email lifecycle required now.

## D. Important files

- `backend/app/models/account.py`: account challenges, login sessions, encrypted mail outbox, and shared rate counters.
- `backend/app/models/user.py` / `refresh_token.py`: verification/deletion fields and refresh-to-session linkage.
- `backend/migrations/versions/003_account_lifecycle.py`: schema upgrade, legacy-cookie revocation, and conservative unverified-address migration.
- `backend/app/services/accounts.py`: token claims, generic recovery, password/email changes, session controls, account deletion, and rate limits.
- `backend/app/services/email.py`: encryption, queueing, SMTP transport, leased delivery, retry/deadline status, and payload clearing.
- `backend/app/jobs/deliver_email.py`: dispatcher process and obsolete-record retention cleanup.
- `backend/app/services/auth.py`, `api/deps.py`, and `core/security.py`: stable session issuance/rotation and live session/membership checks.
- `backend/app/api/accounts.py` / `schemas/accounts.py`: validated account REST endpoints; business rules remain in services.
- `frontend/src/features/accounts/`: recovery, link confirmation, and security/session/delivery screens.
- `frontend/src/auth/AuthContext.tsx`, `services/api.ts`, and existing organization screens: session clearing, typed requests, and verified-email visibility.
- `frontend/e2e/accounts.pw.ts`, `playwright.config.ts`, and `scripts/account_e2e_stack.py`: real Chromium/mailbox-to-browser testing with a disposable database and local SMTP receiver.
- `docker-compose.yml`, `.env.example`, and CI: Mailpit, dispatcher configuration, and automated browser-test setup.

## E. Technical concepts

**Verification versus authentication:** Login establishes password knowledge. Verification demonstrates possession of the separate random challenge delivered to an email address. We allow unverified users to reach profile/security/recovery screens but deny organization resources.

**Purpose-bound tokens:** A verification link cannot reset a password or confirm an email change. Each challenge is random, hashed at rest, attached to a user and email, expires after 30 minutes by default, and is consumed with an atomic conditional database update. Email-change confirmation additionally binds the authenticated actor and checks their current password.

**Sessions and JWTs:** The JWT includes `sid`. The database session has a seven-day absolute deadline and optional revocation timestamp. Refresh changes the cookie secret but keeps the same session ID. A revoked session makes the old JWT unusable despite its otherwise valid signature and expiry.

**Transactional outbox:** Database commit and SMTP acceptance cannot be one database transaction. We commit the account challenge and encrypted pending email together, then send separately. This preserves queued work through transient SMTP failure and avoids synchronous transport timing in public recovery responses.

**Encryption versus hashing:** The challenge table needs only a hash to validate an incoming secret. The dispatcher must recover the email body to send it, so its queued payload is encrypted using Fernet. Its key is derived from the private signing key with a separate domain prefix. Changing that key makes older queued payloads unreadable; resend affected links after coordinated rotation.

**Leases and retries:** A dispatcher claims an eligible row with a lease and conditional update; PostgreSQL additionally skips rows locked by another dispatcher. Delivery failure records a generic code and a later retry. Retry attempts are bounded, and action mail expires with its challenge. SMTP has ambiguous crash/acknowledgement cases: stable Message-ID helps, but duplicate emails remain possible. The account action itself is single-use.

**Rate limits:** Shared atomic counters use fixed time windows and HMAC-derived identity keys. Failed logins and requests for unknown addresses count too. Counters are not process-local, and callers cannot bypass them by supplying an arbitrary forwarded-IP header. Trusted proxy deployment still needs deliberate configuration.

## F. Request flows

1. Registration creates the existing workspace/owner/membership/session and queues a separate verification challenge in the same transaction.
2. The dispatcher sends the private callback URL to SMTP. `queued` means pending; `sent` means SMTP accepted the message, not a guarantee of inbox placement.
3. The recipient opens the fragment-based link and clicks confirmation. The API consumes it and marks the email verified; queueing or SMTP acceptance alone never verifies the user.
4. Recovery requests return the same 202 message for eligible and unknown accounts, with a configurable minimum response duration. Eligible users get a reset challenge through the outbox. Database-load timing is not formally constant.
5. Reset claims the challenge, updates the Argon2id password hash, verifies that bound email, revokes all sessions and outstanding links, queues a notification, and commits. It does not auto-login the user.
6. Email change checks the current password and current address verification, then queues a challenge to the new address and a notice to the old one. Confirmation requires the matching account, token, and fresh password; uniqueness conflicts roll back the entire operation. Success revokes sessions and notifies the old address.
7. Session controls scope IDs to the caller. Individual revocation affects that login; sign-out-all requires the current password. Logout also revokes its stable session.
8. Verified non-owner deletion requires the password and literal `DELETE`. It removes membership/recovery challenges, invalidates access/issued invitations, clears pending payloads, redacts profile and incoming invitation addresses, and retains a reference-safe tombstone. Owner deletion is rejected.

## G. Security and privacy

- No raw account token is returned by recovery APIs or delivery-status APIs. Public action links use URL fragments rather than query strings; successful actions clear them.
- Challenge use is purpose-, user-, and address-bound; resending invalidates earlier links of the same purpose. Expired/replayed/unknown/mismatched links fail.
- Email changes require proof at the new address and password checks at request and confirmation. Another account cannot confirm the token. A target address taken during the waiting period produces 409 with rollback rather than a partial change or lost session.
- Organization access requires verified email independently of invitation possession. Existing-account onboarding and multiple organizations remain Phase 2B work.
- Session checks and rate limits use shared database state. Revocation covers subsequent requests; it cannot undo an operation already completed before revocation.
- SMTP errors are stored as safe codes, not exception text that might contain recipients or secrets. Settings validation suppresses input values in errors.
- Production startup requires HTTPS callback configuration, STARTTLS, and a non-default signing key of at least 32 bytes. Operators must generate that key securely and configure a real provider/from address.
- Deletion redacts current profile fields, removes challenges, clears queued personal payloads, and redacts incoming invitation addresses. A keyed recipient identifier allows cancellation of mail addressed to the deleted user even when queued by a different inviter, without a plaintext recipient index. Minimal IDs, role/tenant references, delivery recipient hashes, and timestamps remain according to the retention policy. This is a technical policy, not a legal-compliance or complete-erasure claim.
- The running maintenance job clears expired rate counters, obsolete account tokens 30 days after expiry, session/refresh/invitation records 30 days after expiry or revocation/consumption, and outbox metadata 30 days after creation. Sent/expired/superseded bodies are cleared earlier. Already delivered external mail cannot be recalled.

The recovery design follows the principles of consistent responses, expiring single-use tokens, side-channel delivery, and normal login after reset described in [OWASP's Forgot Password guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html). Current-password checks for sensitive account changes align with [OWASP authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).

## H. Tests and results

Local verification: **81 backend tests**, **20 frontend component tests**, **7 real Chromium E2E journeys**, Ruff, ESLint, and the TypeScript/Vite production build. `npm audit` reports **zero known vulnerabilities** for the installed dependency graph at this verification point.

Backend coverage includes purpose/expiry/replacement/replay checks, generic unknown-account recovery, current-password checks, cross-account tokens/session IDs, email uniqueness races with rollback, immediate access/refresh revocation, refresh session stability, sole-owner deletion protection, explicit deletion confirmation, redaction, failed-login/recovery rate limits, real SMTP delivery/retry/expiry, password-reset concurrency, and retention that preserves active sessions.

Real Alembic tests cover upgrade/check/downgrade/re-upgrade and seeded legacy data. Existing identities/password hashes remain, addresses become unverified, and old refresh rows are revoked. Browser tests use that real migration chain with SQLite foreign keys enforced.

The seven browser journeys exercise: verification/unlocking plus replay rejection; password recovery and normal sign-in; verified email change; another-browser session revocation and sign-out-all; emailed invitation/separate mailbox verification/member deletion/owner protection; generic unknown recovery/invalid-link errors; and successful verification after its old browser session was revoked. They use a running API and actual SMTP over loopback, not mocked fetch responses.

Follow-up PostgreSQL verification passed all 81 backend tests and Alembic upgrade/check/downgrade/re-upgrade on separate cloudvault_test. Full Compose startup passed after replacing unavailable MinIO images with pinned official source builds; HTTP/storage round-trip and registration-to-Mailpit delivery passed. Production email delivery and remote CI remain unverified; no push or CI dispatch was performed. The browser harness remains a development/test-only process with a temporary database and loopback inbox; it adds no mailbox endpoints to the production API.

## I. Decisions and tradeoffs

ADR-013 chooses live database-backed sessions and conservative migration rather than falsely treating legacy emails as verified. This adds database work to requests but provides revocation across API instances.

ADR-014 chooses an encrypted SQL outbox and a small dedicated email process rather than prematurely implementing all Celery infrastructure. SMTP retry is at-least-once; token consumption and account changes remain transactional and single-use.

ADR-015 adds real browser/mailbox coverage and updates packages identified by npm audit. Vite 8, Vitest 5, React Router 7, compatible plugins, and TypeScript ESLint updates preserve the existing stack. The DOM test setup now imports the Vitest-specific matcher integration. Zero reported advisories is not a claim that all security risks are absent.

## J. Limitations and operation

- One organization per account. Ownership transfer, existing-account invitations, reactivation, and full organization-aware account deletion remain Phase 2B work.
- Local PostgreSQL/Docker checks passed; remote CI and production provider checks remain pending. STARTTLS/provider credentials/from-domain configuration and delivery/incident monitoring are deployment prerequisites. Archived community MinIO requires a maintained production storage decision.
- No MFA or recovery without access to the bound email address. Unverified or inaccessible legacy addresses need a deliberate future support/recovery policy; verification is not bypassed.
- SMTP can duplicate a message after an ambiguous acknowledgement; no exactly-once email guarantee is made.
- Recovery uses generic responses and a minimum duration, not a proven uniform response time under all load conditions.
- Broader abuse controls, token-family replay response, cross-tab refresh coordination, observability, and independent security review remain later work.

For the full development stack, run `docker compose up --build -d`; the Mailpit web inbox is at `http://localhost:8025`, with SMTP on 1025. The [official Mailpit Docker documentation](https://mailpit.axllent.org/docs/install/docker/) describes these ports. The dispatcher is included in Compose.

For directly installed development: install backend requirements, apply `alembic upgrade head`, run the API, start the local SMTP inbox, and run `python -m app.jobs.deliver_email` in another backend terminal. Keep backend/dispatcher signing-key and SMTP settings synchronized. View safe delivery state under **Account security and email**; resend expired/failed action links as appropriate.

Run browser tests from frontend with `npx playwright install chromium` once, then `npm run test:e2e`. The test stack uses ports 43000/48000/41025/48025 and a disposable database, never the application database.

## K. Interview questions

**Why isn't a valid JWT enough after logout?** Its signature says it was issued by the server; it does not reflect later revocation. `sid` links it to a live database session check.

**Why keep one stable ID during refresh rotation?** The cookie secret changes while the login remains the same manageable session. Revoking that session invalidates all its rotated refresh tokens and access tokens.

**Why encrypt mail bodies but hash reset tokens?** Validation only needs a hash. Delivery needs the original body, so it must be recoverable by the dispatcher while remaining unreadable to a database-only reader without the key.

**What if SMTP accepted mail but the dispatcher crashed before recording success?** A retry can send it again. We use stable Message-ID and single-use challenges, document at-least-once transport, and never claim perfect exactly-once delivery.

**How does an email-change race avoid partial revocation?** Confirmation holds the user lock and performs address update, challenge consumption, session revocation, and notification queueing in one transaction. A unique-email failure rolls it all back; a regression test confirms the original session still works.

**How did you verify that the feature is real?** API/database tests cover security failures and transactions; real SMTP integration captures delivered messages; Chromium journeys open actual delivered links against a running migrated backend.

Next implementation: Phase 2B, only on explicit instruction. Phase 2 and Phase 2A changes remain uncommitted, with no push performed. Suggested commit for the current combined pending work: `feat: add organizations and verified account lifecycle`.
