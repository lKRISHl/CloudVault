# Phase 10 — File Search

Implemented and locally verified on 2026-10-15. Schema: 010_file_search.
Phase 9 is committed as 0551f25; Phase 10 is committed as d4aa3e1.

## A. What was built

Search files across the selected workspace or within root/a selected folder. Filter
by upload status, transfer method, creator, exact declared MIME and byte range. Sort by
filename, size or created/updated date; navigate result pages, open the containing
folder and download completed files through the existing authorized flow.

## B. Why

Folder browsing alone becomes cumbersome as a workspace grows. Filename search and
metadata filters locate files without processing object bytes or prematurely adding
AI/full-text search. Database indexes support useful query paths while permission and
result identity remain owned by CloudVault.

## C. Architecture

GET /api/v1/files/search delegates to FileSearchService with a strict typed query model.
It applies a separate persistent rate budget, verifies current workspace membership and
checks the selected folder's tenant/ancestor chain. Every statement includes the active
tenant and excludes cleanup tombstones. Folder names join on folder ID and tenant ID,
avoiding one additional query per result. Public metadata excludes storage identities.

Filename terms normalize NFC, trimming and case folding against stored name_key.
LIKE wildcard characters are escaped and values remain bound parameters. Sort columns
and direction are whitelisted; UUID breaks ties in the same direction. Query returns
limit+1 rows for has_more, without a full count query.

010_file_search adds partial live-file tenant B-tree indexes for name/size/created/
updated and status/name ordering. PostgreSQL uses a partial name_key GIN index with
pg_trgm; SQLite omits the PostgreSQL-specific index in DDL/schema comparison. The
migration changes indexes only and leaves the shared extension installed on rollback.

## D. Important files

- backend/app/schemas/search.py: strict query/result models.
- backend/app/services/search.py and api/files.py: scoped service and no-store route.
- backend/app/models/file.py and migrations/versions/010_file_search.py: indexes.
- backend/migrations/env.py: explicit SQLite handling for the PostgreSQL-only index.
- backend/tests/api/test_search.py and test_search_migration.py.
- frontend/src/features/search/FileSearchPage.tsx, services/api.ts and types/index.ts.
- frontend/src/components/AppShell.tsx, ui/Icon.tsx and features/folders/FoldersPage.tsx.
- frontend/src/__tests__/FileSearch.test.tsx and e2e/search.pw.ts.
- scripts/upload_smoke.py, CONTINUE.md and ADR-027.

## E. Technical concepts

Literal substring search is distinct from SQL wildcard, regex, fuzzy, file-content or
semantic search. A percent/underscore in the search term matches the actual character.
Case folding supports examples such as Straße/STRASSE; NFC handles composed/decomposed
Unicode. Accents remain significant. Folder scope covers direct children, not a subtree.

Trigram indexes can support substring matching; short/common terms may still require
large scans. B-tree indexes support tenant-filtered ordering and page retrieval. Planner
choice depends on statistics, selectivity and pending index maintenance. See
[PostgreSQL pg_trgm documentation](https://www.postgresql.org/docs/16/pgtrgm.html).

Pending sizes/types are declarations. Uploaded size equals the declaration through
existing verified-upload constraints; MIME declarations never establish detected type
or malware safety. Pending status includes retained cancelled multipart metadata until
cleanup hides it. Results expose the existing Cancelled badge where applicable.

## F. Request flow

1. Open Search files from navigation, or Search this folder from folder browsing.
2. Submit filename and optional filters/order/page size. The browser builds encoded
   query parameters and cancels obsolete requests.
3. Server validates input, checks current membership/folder scope and queries only live
   records within the selected tenant.
4. Return public metadata, direct folder context, offset/limit and has_more with no-store.
5. Next/Previous preserve submitted filters; new submissions or cleared filters reset
   to the first page. Workspace/folder context changes reset the search component.
6. Open folder navigates to normal browsing. Download uses the existing current-member,
   provider-checked native attachment flow; search itself does not issue capabilities.

## G. Security

Client cannot choose tenant scope. Foreign/nonexistent folder IDs fail identically;
foreign creator IDs produce no matching tenant files rather than account enumeration.
Cleaned records/private provider references are excluded. Query rejects unknown keys,
control characters, invalid sort/filter enums, incompatible folder/scope, reversed size
ranges, pages above 100 and offsets above 10000. SQL injection/wildcard expansion tests
fail closed. Separate budgets permit 1200 identity/4800 IP searches per configured window
(15 minutes default).

Client query keys include workspace/user/submitted filters/page. Session-generation
guards and component remounting prevent stale workspace responses/results. Search
values are not persisted in local storage. GET terms can appear in operational access
logs; production requires reviewed query logging/redaction/retention.

Current verified members share workspace read access. Phase 12 must enforce resource
ACLs inside search/list predicates before pagination, folder context and counts. Files
remain unscanned; download capability/version limitations remain unchanged.

## H. Verification

- 214 backend tests pass on SQLite and disposable PostgreSQL cloudvault_phase10_* with
  actual MinIO enabled. Migration fixtures create independent temporary databases.
- Search tests cover normalized Unicode/case folding, literal percent/underscore,
  injection strings, empty results, scope/creator/type/size/status/method filters,
  uploaded metadata, hidden cleanup records and private fields.
- Whitelisted sorting, real tie-breaking and pagination pass; unauthenticated/unverified,
  foreign tenant/folder, revoked-member, invalid-query and rate-budget cases fail closed.
- Migration tests preserve existing files/accounts and verify schema alignment plus
  safe populated downgrade/re-upgrade. PostgreSQL extension/GIN and SQLite B-tree
  handling are tested rather than substituted.
- A 5001-row synthetic PostgreSQL fixture confirms selective filename GIN and size-order
  index paths after statistics and GIN pending-list maintenance. The initial freshly
  bulk-loaded GIN query used a sequential scan; flushing pending entries changed the
  chosen plan. No planner settings were forced and no throughput benchmark is claimed.
- 60 frontend tests, ESLint, TypeScript/Vite build, Ruff and whitespace checks pass.
  Search tests cover controls, paging reset, workspace cache separation, selected-folder
  scope, empty/error/retry, validation, encoding and stale response rejection.
- All 15 Chromium/SMTP/storage journeys pass. Search journey covers real uploaded/pending
  records, folder search, literal percent term, filtering, paged sorting, exact downloaded
  bytes, reset, mobile overflow and switched-workspace isolation.
- Docker rebuild/start, HTTP/private bucket/mc/adapter smoke, real SMTP/upload/resume/
  download/search/filter/sort/pagination, schema check and maintenance tick pass.
  Live schema is 010_file_search with no drift. Unique demo account/workspace/two files remain.
- TypeScript caught an unsupported Testing Library matcher option; it was removed and
  final tests/lint/build passed. Browser-owned bucket cleanup completed; manifest is absent.
  Remote CI, production load/provider/browser certification remain unrun.

## I. Decisions and tradeoffs

ADR-027 records literal metadata search, shared tenant-read policy and indexing. Stable
ordering is not a transaction snapshot: concurrent inserts/cleanup can shift offset
pages. Deep offsets are bounded rather than described as indefinitely scalable. Short
terms are supported with their scan cost disclosed; production needs workload/query-plan
monitoring, database timeout/abuse review and tuning.

## J. Operations and limitations

Search is at http://localhost:3000/app/search. UI pages are 5/25/50 rows; API defaults to
25 and caps at 100, offset maximum 10000. Filename query maximum is 128 characters.
Refine filters at the paging boundary. No global count, consistent snapshot, recursive
folder search, fuzzy/accent folding, tags, full-text or AI search is introduced.

Back up before alembic upgrade head. The ignored backup is
.local/backups/cloudvault-before-phase10.sql. Docker startup applies 010_file_search.
PostgreSQL needs permission to install pg_trgm or prior operator provisioning. Downgrade
to 009 removes only search indexes and preserves data/shared extension; older rollback
still inherits upload-reference/intent/tombstone guards. Index creation is regular DDL
and may block writes on a large database; plan production migration timing separately.

Run docker compose up --build -d, python scripts/docker_smoke.py and
python scripts/upload_smoke.py. The latter now checks live search/filter/order/pages as
well as transfers and retains unique development data. Tests use disposable databases
and owned buckets, never destructive application fixtures.

Private ACLs/sharing, trash/versions, scanning, quotas and AI remain later. Maintained
storage, production SMTP/MFA, provider lifecycle/IAM/backup/monitoring, remote CI and
deployment/security hardening remain gates. A successful local search test is not a
production performance or industry-readiness certification.

## K. Interview discussion

- Why use literal substring matching? Filename search must treat punctuation as data
  and avoid exposing SQL/regex operators through user input.
- Why add a UUID tie-breaker? Many files can share a name, size or timestamp; ordering
  must be deterministic for a fixed dataset across pages.
- Why both GIN and B-tree indexes? They support different substring and ordered
  retrieval paths; planner/statistics/workload determine the actual choice.
- What does offset pagination miss? It does not preserve a snapshot across concurrent
  changes and grows more expensive with deep pages; keyset/snapshot designs are later
  scaling options, not hidden guarantees.
- How do future ACLs affect search? Permission predicates must run before pagination
  and folder-context exposure so inaccessible metadata/counts cannot leak.
