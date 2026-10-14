# Phase 5 — Object Storage

Implemented and locally verified on 2026-10-14. Phase 6 has not started.

## A. What we built

- An internal ObjectStorage protocol and an S3-compatible Boto3 adapter.
- UUID-only tenant/file/object keys, isolated tenant scopes and safe provider errors.
- Private local bucket provisioning, complete storage configuration and secret redaction.
- Bucket checks, conditional small writes, metadata inspection, bounded reads and deletion.
- Real MinIO contract tests with disposable buckets and a configured-adapter Docker smoke.

## B. Why we built it

The file model should not depend on one vendor's SDK or store file bytes in PostgreSQL.
The adapter gives later upload/download services a defined storage boundary while
keeping metadata, authorization and object transfer as separate responsibilities.
Storage operations are real; this phase does not claim a user upload flow exists.

## C. Architecture

`ObjectStorage` defines async bucket/put/head/read/delete/close operations. The
S3 adapter uses Signature V4, configured addressing style and bounded SDK connection
and read timeouts with at most two attempts. Blocking SDK calls run on executor
threads, so storage I/O does not run on the async event loop.

Each adapter is scoped to a tenant UUID. ObjectRef requires UUID tenant/file/object
identities and derives `tenants/{tenant}/files/{file}/objects/{object}`. Filenames,
folder paths and arbitrary request keys never determine storage location. Distinct
object IDs provide a foundation for future upload attempts/version identity.
Callers must first authorize resource membership and file access through services;
key prefixes and adapter scope do not replace those checks or provider IAM.

No new database migration is needed. The app remains at `006_files`; storage references
and verified file state will be attached transactionally by the upload phase.
The existing local MinIO/source-build services remain. Compose provisions the
development bucket and sets its anonymous policy to none before the API starts.

## D. Important files

- `backend/app/storage/base.py`: protocol, reference/info types, limits and safe errors.
- `backend/app/storage/s3.py`: SDK configuration and tenant-scoped implementation.
- `backend/app/core/config.py`, `.env.example`: storage validation and secret fields.
- `backend/app/jobs/check_storage.py`: actual configured-adapter smoke with cleanup.
- `backend/tests/test_storage.py`: input, scope, SDK contract and failure checks.
- `backend/tests/test_storage_integration.py`: real provider tests in unique buckets.
- `docker-compose.yml`: complete S3 settings and private bucket setup.
- `scripts/docker_smoke.py`, `.github/workflows/ci.yml`: adapter/private-access verification.
- `backend/requirements.txt`, `pyproject.toml`: Boto3 dependency.

## E. Technical concepts

**Logical identity versus object key:** A file's display name can change without
changing its storage identity. A UUID-only key avoids user-controlled path traversal
and accidental cross-tenant path construction. Tenant checks reject foreign refs
before network access.

**Conditional creation:** Small internal writes send If-None-Match `*`, preventing
replacement of an existing object. A precondition/concurrency conflict becomes a
safe ObjectConflictError. Lost acknowledgements can still make a successful write
appear conflicted on retry; future upload completion must reconcile actual objects.
[Boto3 conditional-write reference](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/bucket/put_object.html).

**Bounded internal transfers:** Small helpers accept at most 1 MiB. Reads inspect
size, handle zero-length objects, then use a bounded range with If-Match against
the observed ETag. The adapter rejects oversized or truncated bodies and closes
streams on success/failure. GET opening, consuming and closing happen on one worker
so cancellation of the awaiting task still lets cleanup finish. ETags are provider
identifiers, not a guaranteed SHA/content-integrity checksum.
[Boto3 read reference](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/get_object.html).

**Error boundaries:** Object-not-found and conditional conflicts have explicit safe
types; permission, transport and other provider failures fail as StorageUnavailableError.
Raw SDK messages are suppressed. Missing buckets do not pass the bucket check.
Deletes are idempotent for absent objects in the tested unversioned local deployment.

## F. Flows

1. Compose starts MinIO, creates the development bucket if absent and disables
   anonymous access; the API receives endpoint, credential, bucket and region settings.
2. An authorized internal service constructs its tenant-scoped adapter and UUID ref.
3. A small write conditionally creates an object. HEAD returns actual storage length,
   content type, ETag and timestamp; these facts do not by themselves establish safe
   MIME or malware clearance.
4. A bounded read verifies size and the observed object generation before returning
   bytes. Deletion removes the current local object; the service closes its client.
5. Operator smoke writes a unique object, checks actual metadata/content, deletes it
   and verifies absence. Cleanup is attempted even after ambiguous write acknowledgement.

## G. Security

The bucket is private and anonymous reads/listing are rejected in real tests.
Storage credentials use SecretStr and are absent from public API responses. Endpoint
configuration is operator-controlled, restricted to HTTP(S) origins without embedded
credentials, path, query or fragment. Production custom endpoints require HTTPS and
reject the default local password; custom endpoints require a complete credential pair.
Native AWS endpoints can use the SDK credential chain. Missing/partial settings fail
validation instead of silently selecting unrelated storage.

The adapter exposes no public upload/download/delete endpoint. Resource services must
recheck tenant membership and resource authority before constructing refs. Production
needs reviewed IAM/least-privilege credentials and provider-specific public-access
controls; development root credentials are not a production deployment design.

## H. Verification

- 158 backend tests pass with SQLite and PostgreSQL plus actual local MinIO enabled.
  PostgreSQL uses disposable `cloudvault_phase5_test`, never application data.
- 24 storage unit/contract cases cover invalid/partial settings, redaction, production
  TLS/default credentials, disabled storage, AWS configuration, keys/tenant scope,
  operation parameters, stream cleanup, size bounds, zero-length/truncated reads,
  missing/conflict/permission/provider/connection errors and foreign-scope rejection.
- Three real MinIO tests own uniquely named disposable buckets. They exercise binary
  and empty objects, actual HEAD/read/delete, absent delete, name overwrite prevention,
  anonymous GET/list denial, concurrent creation, missing buckets and invalid credentials.
- Ruff and whitespace checks pass. Docker rebuild and actual adapter/HTTP/private-bucket
  smoke pass; application schema remains `006_files` with no differences.
- Phase 4's 31 frontend tests and 11 browser journeys remain the last frontend
  verification; Phase 5 adds no frontend behavior. Docker rebuild includes frontend build.
- An initial image export interrupted Docker and affected concurrent tests. The stack
  was restored and affected checks rerun successfully, with builds/tests run separately.
- CI now includes actual disposable-bucket adapter tests, but no push or remote CI
  dispatch was performed. Phase 4 and Phase 5 remain uncommitted.

## I. Decisions and tradeoffs

ADR-021 records the protocol/adapter boundary, UUID keys, private bucket, bounded
small operations and conditional creation. The S3 SDK runs in threads rather than
introducing another async client dependency. Cancellation cannot stop an in-flight
SDK write; completion/reconciliation and cleanup must account for that later.
SDK timeouts/retry limits bound individual operations, not a hard aggregate wall-clock
deadline under every DNS/network condition.

## J. Operation and limitations

Run `docker compose up --build -d`, then `python scripts/docker_smoke.py`. The latter
checks the UI/API, private bucket and both mc and application-adapter object round trips.
The adapter smoke can also run with `docker compose exec -T backend python -m app.jobs.check_storage`.

For a direct setup, install backend requirements and configure S3 variables from
`.env.example` in the backend environment. TLS follows the endpoint scheme; the former
unused S3_USE_SSL variable is removed from the example. Use S3_ADDRESSING_STYLE for
path/virtual/auto addressing. Existing local bucket data is preserved by provisioning.

To run real storage tests from backend, set TEST_S3_ENDPOINT, TEST_S3_ACCESS_KEY and
TEST_S3_SECRET_KEY for a development/test provider, then run
`python -m pytest tests/test_storage_integration.py -q`. Each test creates/deletes its
own bucket; credentials need that test-only capability. Without these variables,
the three integration cases explicitly skip. The ordinary unit tests need no provider.

This is the storage foundation. User uploads/presigned transfers and completion
validation are Phase 6; downloads Phase 7; multipart/resume/abandoned cleanup later.
There are no persisted object references, readiness state changes, public transfer
URLs, automatic storage health/readiness probe, object lifecycle rules or CORS upload
policy yet. The normal readiness endpoint still checks the database; operator smoke
checks storage. No new database migration is introduced in Phase 5.

Provider-specific encryption, IAM, public-access blocking, production S3/R2 verification,
maintained storage deployment, backup/restore and monitoring remain deployment gates.
Community MinIO is archived and is the local development provider only. Delete semantics
for versioned buckets need explicit version/lifecycle handling in later phases; a delete
marker is not proof that all historical bytes have been purged. Existing SMTP, remote CI,
MFA, security and deployment-hardening limitations remain recorded in CONTINUE.md.

## K. Interview questions

**Why UUID-only keys?** They preserve identity independently of filenames/folder moves
and eliminate user-controlled key construction. Authorization still belongs to services.

**Why keep file bytes out of PostgreSQL?** Metadata and object transfers have different
storage and operational requirements; large transfers should go directly to object storage.

**What proves this adapter works?** Real MinIO tests and the configured Docker adapter
smoke exercise actual objects and failure cases; SDK stubs separately verify parameters.

**How do duplicate writes behave?** Conditional creation prevents replacement, while
ambiguous acknowledgements require inspection/reconciliation rather than an exactly-once claim.

**Is this storage implementation production certified?** No. The local contract is
verified; a maintained provider and production policy/deployment checks still need evidence.

Next: Phase 6 — Basic Upload, only on explicit instruction.
