# Phase 7 — Basic Download

Implemented locally on 2026-10-14. No new database migration; schema remains 007_uploads.

## A. What was built

Verified workspace members can download completed uploads from the file browser. POST /api/v1/files/{file_id}/download-url returns current file metadata, a short-lived signed GET URL and expiry. Pending uploads have no download control and are rejected by the API. The file is delivered directly by private object storage.

## B. Why

CloudVault must authorize file access while keeping file bytes out of the API and PostgreSQL. Native browser downloads avoid buffering the file in SPA memory and use the provider's attachment response.

## C. Architecture

Routes delegate to DownloadService. It applies the existing persistent identity/IP limiter, verifies current membership, looks up the file using both file ID and workspace ID, verifies the folder chain and stored bucket, and inspects the provider object. Size, SHA-256, ETag and generic content type must still match the completed record. Membership is rechecked after inspection and signing. Only then is a ticket returned.

S3ObjectStorage signs get_object with ResponseContentDisposition, ResponseContentType and ResponseCacheControl overrides. It uses the existing internal inspection endpoint and separate browser-facing signer endpoint. UUID-only object references and adapter tenant validation remain enforced.

## D. Important files

- backend/app/services/downloads.py and schemas/downloads.py: authorization and ticket contract.
- backend/app/api/files.py: service delegation and no-store response.
- backend/app/storage/base.py and s3.py: signed GET contract and attachment headers.
- backend/app/core/config.py, .env.example and docker-compose.yml: DOWNLOAD_URL_SECONDS.
- frontend/src/services/api.ts: scoped ticket request and session-generation guard.
- frontend/src/features/folders/DownloadButton.tsx and FileList.tsx: completed-file action, busy/error/manual-retry state and unscanned disclosure.
- backend/tests/api/test_downloads.py, test_storage.py and test_uploads_integration.py: permission, signing and actual provider checks.
- frontend/src/__tests__/FileList.test.tsx and e2e/uploads.pw.ts: stale-response protection and real browser byte verification.

## E. Technical concepts

A signed URL is a bearer capability, not a public bucket. Its URL necessarily contains the opaque object key and signature; do not log, persist or share it. File metadata responses continue to hide internal object/bucket references. The API returns no-store and the signed GET overrides provider cache control to no-store.

Content-Disposition uses attachment, an ASCII fallback and RFC 5987 UTF-8 filename. Controls, path separators and quote injection are sanitized. Content-Type is application/octet-stream regardless of the untrusted declared MIME. This prevents an intentional inline preview; it does not make unscanned bytes safe.

ETag is compared as an additional provider identity attribute, not represented as a cryptographic hash. The persisted SHA-256 is the integrity comparison. The signing fields follow the [official Boto3 GET object contract](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/get_object.html).

## F. Request flow

1. A member clicks Download on an uploaded file.
2. API authentication and selected workspace are checked; service rate limits and current membership apply.
3. Tenant-scoped metadata and provider HEAD must match the completed upload.
4. Service signs an attachment GET and rechecks membership before returning it.
5. The SPA rejects aborted/stale session responses, then creates a temporary native anchor with no-referrer and noopener/noreferrer. No bearer header is added to the object request.
6. The browser download manager receives storage bytes; the temporary link is removed immediately.

No fake percentage or successful-delivery counter is reported. Issuing a ticket does not prove a download finished.

## G. Security and policy

All verified active members currently share read access inside a workspace; creators/managers have separate write authority. Download authorization does not require can_write. Granular private-folder/resource ACLs are Phase 12. Foreign/missing IDs return 404; pending/missing/changed objects fail closed with 409. Provider/signing errors return safe 503 responses. Existing identity/IP limits apply to download grants (default 10/100 per 15 minutes), independently of upload categories.

The browser journey checks actual GET bytes, attachment filename, absence of CloudVault Authorization/cookies/referrer, and reload/workspace isolation. Provider tests also reject modification of a signed response-header query parameter.

## H. Verification

See CONTINUE.md for final test counts and current runtime verification. Local checks include the full SQLite/PostgreSQL backend suites with actual MinIO, frontend tests/lint/build, and Chromium/SMTP/storage journeys. Cases cover owner/member read access, tenant isolation, pending/missing objects, changed size/checksum/ETag/type, bucket drift, safe errors, rate limits, revocation during inspection and signing, Unicode/header-safe names, URL lifetime bounds, actual signed GET bytes and tampering rejection.

Disposable test databases and unique test buckets are used. The application database/bucket are never cleared. No remote CI or production provider certification was performed.

## I. Decision

ADR-024 records short-lived checked direct attachment downloads. There is no new persisted download URL, event/count table, streaming API or migration.

## J. Operation and limitations

Run docker compose up --build -d after source changes. Select a verified workspace, open Files & folders and click Download on an uploaded file. DOWNLOAD_URL_SECONDS defaults to 300 and accepts 30–900 seconds. Compose forwards the setting; direct API setup reads backend environment. Provider credentials can expire earlier than the nominal URL lifetime.

Issued URLs are reusable until expiry and cannot be immediately revoked by app logout/membership removal. Permission changes prevent new grants; in-flight native downloads may continue. A provider administrator can replace an object after the HEAD check: current application writes are conditional, but these GET URLs do not pin an object version. Immutable/version-specific reads and version history belong to later version/provider work. No one-time claim or complete-delivery audit is made.

Files remain unscanned; there is no safe inline preview, MIME detection, password-protected sharing, multipart/resume UX, aggregate quotas or download completion telemetry. Native error handling after the handoff belongs to the browser/provider; retry requests a fresh authorized grant. Safari/Firefox and production S3/R2 behavior still need deployment verification. Existing maintained-storage, production SMTP, MFA, security review, backup/monitoring and remote-CI gates remain.

## K. Interview discussion

- Why use signed object transfers? To separate authorization from byte delivery and avoid API bandwidth/memory costs.
- Why check HEAD first? To refuse grants for missing or changed objects while retaining metadata as a verified record.
- Why attachment/octet-stream? Stored declarations and unscanned bytes cannot justify inline execution.
- Can logout revoke a URL? Not immediately; its expiry bounds the capability and new issuance rechecks access.
- Does HEAD guarantee subsequent bytes? Not against out-of-band replacement; version-pinned storage reads are a later requirement.
- Can an admin write flag determine downloads? No; workspace read policy authorizes members independently of write permissions.

Final verification: 186 backend tests pass separately on SQLite and PostgreSQL with real MinIO; 42 frontend tests and 13 Chromium/SMTP/storage journeys pass. Ruff, ESLint, TypeScript/Vite, whitespace checks and full Docker rebuild pass. Docker SMTP/upload/download exact-byte checks succeed, and Alembic reports no new upgrade operations. Phase 8 remains unstarted. Changes remain uncommitted.
