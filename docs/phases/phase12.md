# Phase 12 — Permissions / RBAC

Implemented and locally verified on 2026-10-15. Schema: 012_permissions. Final verification is recorded below.
Phase 11 is committed as fa6a27e; Phase 12 remains uncommitted.

## A. What was built

Workspace/private visibility, explicit member viewer/editor grants, resource permission
management and permission-aware folder/file access. The rules apply to browsing, folder
context, search, download grants, upload controls, external publishing and public shares.
Editors can rename completed files; folder editors can rename and create content within
that folder. Creators/managers control moves, permissions and external publication.

## B. Why

Workspace membership alone should not expose every resource. A private file or folder
needs server-side authorization at every route that can disclose metadata or issue a
storage capability. Filtering after pagination can reveal counts or produce misleading
pages, so visibility predicates must participate in the database query itself.

## C. Architecture

File and Folder receive visibility with workspace as the migration/default policy.
ResourceGrant references one file or folder, a tenant-bound membership and a viewer/editor
role. Database checks enforce exactly one resource and valid roles; partial unique
indexes prevent duplicate grants, while the actor lookup index supports authorization.

PermissionService centralizes local visibility, grant predicates, effective folder
visibility, resource read checks, write/management decisions, permission mutation and
external-link invalidation. Current active verified membership remains mandatory.
Owners/admins retain organization-wide resource management. Creators retain management
of their resource but must still be able to traverse its containing folder boundaries.

A recursive SQL CTE starts at readable root folders and includes children only when each
child is locally readable, bounded by the existing depth limit of 64. File queries require
local file visibility and either root placement or an effective readable containing folder.
Search and lists apply these predicates before ordering/offset/limit+1 and folder context.
Editor annotations are loaded in one grant query per returned page, avoiding a grant
lookup for each result. Ancestor validation remains bounded and rechecks readable folders.

Permission writes take the existing tenant write lock, recheck management authority,
validate the target's active verified membership and commit with relevant link revocation.
Concurrent grant upserts serialize and preserve one grant row. Member removal deletes
their grants in that workspace; account deletion removes memberships and cascades grants.
Rejoining cannot restore the removed grants automatically.

Downloads recheck resource ACLs before and after provider work as well as current
membership. Upload retries/completion and multipart controls retain creator-only session
authority and additionally require readable resource/ancestor scope and writable parents.
External publishing requires resource management, so editors cannot publish. Public shares
recheck their publisher's current effective file access under tenant serialization.

## D. Important files

- backend/app/models/permission.py, models/file.py, models/folder.py and migrations/versions/012_permissions.py.
- backend/app/schemas/permissions.py, services/permissions.py and api/permissions.py.
- backend/app/services/folders.py, files.py, search.py, downloads.py, uploads.py, multipart.py and shares.py.
- backend/app/services/organizations.py and app/main.py.
- backend/tests/api/test_permissions.py, test_permissions_migration.py and migration_seed.py.
- frontend/src/features/permissions/PermissionsPage.tsx and features/folders/RenameFile.tsx.
- frontend/src/features/folders/FoldersPage.tsx, FileList.tsx and features/search/FileSearchPage.tsx.
- frontend/src/services/api.ts, types/index.ts, app/App.tsx and __tests__/Permissions.test.tsx.
- frontend/e2e/permissions.pw.ts, scripts/upload_smoke.py, CONTINUE.md and ADR-029.

## E. Technical concepts and exact policy

Workspace visibility grants local read access to current verified members. Private visibility
requires creator/manager authority or an explicit viewer/editor grant. Every containing
folder must also be readable; a direct file grant never bypasses a private ancestor.

Viewer means read/download. Editor includes viewer and resource-local editing: completed
file rename, folder rename and content creation within an editable folder. There is no
inherited editor role: editing a parent does not allow editing someone else's child resource.
Workspace-visible children become readable through an accessible parent, but a separately
private child still requires its own local authorization. Creation gives the creator
management of the new content, subject to ancestor boundaries.

Creator/manager authority controls visibility/grants, folder moves and external publishing.
An explicit viewer grant cannot reduce implicit creator/manager rights; removing a grant
does not deny workspace visibility. Owner/admin are current workspace membership roles;
viewer/editor are resource grants, not new global identity roles.

## F. Request flow

1. Choose Permissions on a managed file/folder in browsing or search. The page identifies
   the resource, current visibility and explicit grants.
2. Switch to Private or Allow workspace readers. Existing content defaults to workspace
   visibility, preserving the previous read policy until deliberately changed.
3. Select an active verified workspace member using candidate pages of 25; assign Viewer
   or Editor. Grant listings also use pages of 25 with a bounded offset.
4. Read queries evaluate effective ACLs before returning rows, breadcrumbs or folder names.
   Denied resources return not found rather than disclosing private names.
5. Viewers download through the checked storage flow; editors can rename completed files
   without changing object identities, bytes, checksums or upload receipt integrity.
6. Remove explicit access or change visibility. Permission changes revoke external links
   for the file or folder subtree in the same transaction. No-op visibility changes leave
   links intact; grant updates/removals conservatively revoke affected links.
7. Folder moves require creator/manager control and a writable destination, validate hierarchy,
   and revoke subtree links. Moving can change effective ancestor restrictions; the UI states
   that consequence before the action.

## G. Security

Client-supplied tenant IDs are not accepted. Resource queries, grants, membership lookup
and link invalidation are tenant-scoped. Membership foreign keys bind grant recipients
to the same organization. Invalid/foreign/removed/unverified targets cannot receive new
grants. Unknown visibility/role/extra fields are rejected; owner/admin cannot be submitted
as resource-grant roles. Editors cannot escalate to management or publish external links.

Search/list predicates protect filenames, folder names, breadcrumbs and has_more. A hidden
row does not consume a visible result page. Private ancestor traversal also protects direct
IDs, upload grants/completion and downloads. Loss of an ACL during provider inspection
blocks subsequent signing; already issued provider capabilities remain usable until expiry.

Permission mutations have persistent budgets of 100 identity/500 IP per configured window
(default 15 minutes); completed-file renaming uses ordinary account category limits.
Resource API successes/errors use no-store/no-referrer. Management caches/remounts include
workspace/user/resource; stale scoped responses are rejected by existing session guards.
Previously received metadata is not remotely erased; live roster/ACL cache synchronization
is still future realtime work. Production timeout/abuse/query-load review remains required.

## H. Verification

- 235 backend tests pass on SQLite (240.64 seconds) and disposable PostgreSQL
  (241.51 seconds), with actual MinIO integration enabled. Fixtures use independently
  owned databases/buckets and never destructive access to application data.
- Private-file and ancestor hiding, visible pagination, viewer/editor/management boundaries,
  foreign targets/role escalation, grant revocation/member lifecycle, concurrent upserts,
  subtree share revocation and download ACL loss during provider work are covered.
- Pending upload retry/completion denies a creator who loses parent access. Completed-file
  renames preserve storage references, and direct descendant grants cannot bypass ancestors.
- Permission migration tests preserve old content/accounts/default visibility, verify empty
  rollback/re-upgrade and refuse private/grant policy loss. All earlier migration suites pass.
  Historical fixtures now seed historical schemas directly and restore head after refused
  chain downgrades; current services are no longer used against pre-ACL table definitions.
- All 72 frontend tests, ESLint, TypeScript/Vite build, Ruff and whitespace checks pass.
  Visibility, grants/removal, management denial/retry, scoped cache identity, paginated
  member selection and rename conflict/retry are exercised.
- All 17 Chromium/SMTP/storage journeys pass (reported 1.2 minutes). The new two-user
  journey verifies actual viewer download bytes, editor rename, management-control hiding,
  private ancestor protection, explicit ancestor access, final revocation and mobile layout.
- Rebuilt Docker HTTP/private-bucket/mc/adapter smoke and actual SMTP/basic/multipart
  transfers/search/sharing/ACL checks pass. A second verified member demonstrates hidden
  private search/detail, viewer download exact bytes, editor rename, management denial and
  removed access. Live schema is 012_permissions with no drift; maintenance tick succeeds
  with zero eligible records. All eight long-running services are healthy/running.
- Browser-owned bucket cleanup completed; disposable PostgreSQL verification data is removed.
  Ignored pre-upgrade backup and .local/phase12-*.log evidence are retained. Unique smoke
  development accounts/content remain. Remote CI, production provider/security/load and
  Safari/Firefox certification remain unrun.

## I. Decisions and tradeoffs

ADR-029 records default-preserving resource visibility, mandatory ancestor read gates,
resource-local editor grants, creator/manager control and conservative share revocation.
An allow-list plus workspace/private policy avoids ambiguous deny/override precedence.
It requires separately granting private ancestors and does not implement inherited editing,
groups, custom roles, ownership transfer per file or organization-wide viewer roles.

Recursive visibility is evaluated by the database rather than by fetching every file and
filtering in application memory. Its cost depends on the hierarchy and grant workload;
existing trigram/B-tree paths remain useful but do not prove production ACL query throughput.
Tenant write serialization favors straightforward consistency over measured write scaling.

## J. Operations and limitations

Back up before alembic upgrade head (012_permissions); Docker startup migrates automatically.
The ignored pre-upgrade backup is .local/backups/cloudvault-before-phase12.sql. Existing
files/folders become workspace-visible and existing accounts/content remain intact.
Downgrade refuses private visibility or any explicit grant rather than silently reopening
private content or discarding access policy. Restore the pre-upgrade backup for rollback
that cannot represent the current policy. SQL backups cannot restore provider object bytes.

Run docker compose up --build -d, python scripts/docker_smoke.py and python scripts/upload_smoke.py.
The latter creates unique verified development accounts/content and checks private-file
hiding, actual viewer downloads, editor rename, management denial and access removal.
Tests always use owned disposable databases/buckets, never the application database.

Use Permissions from /app/folders or /app/search. Member and grant pages are 25 rows;
permission-list offsets cap at 10000. Resource UUIDs identify recipients whose names are
not on the currently loaded candidate page. Folder grants are resource-local; required
private ancestors must be granted separately. Managers are trusted to access private content.
Readable-name collisions remain generic conflicts even if another sibling is private;
the namespace does not promise immunity from existence guesses through attempted creation.

Issued storage URLs/received bytes cannot be recalled by ACL revocation. Browser caches
may retain prior authorized metadata until refresh; no realtime deletion notification is
claimed. Grant metadata has no dedicated audit/history/retention scheduler yet. Trash (13),
versions (14), previews (15), scans (17), realtime (18), quotas (19), audit (20), AI (21+),
maintained production storage, MFA, SMTP, remote CI, backup/restore and deployment hardening
remain pending. Community MinIO is local-only and archived.

## K. Interview discussion

- Why filter before pagination? Hidden rows must not affect visible page contents or
  has_more, and inaccessible folder context must never be attached to a search result.
- Why require all ancestors? A direct descendant grant must not bypass a private container.
- Why distinguish editing from management? Delegating rename/content creation should not
  permit granting further access, relocating protected subtrees or publishing external links.
- What happens when a member leaves? Membership denial, explicit grant deletion and published
  link revocation prevent reactivation from silently restoring prior resource access.
- What remains after revocation? Previously issued storage capabilities and received bytes
  have separate lifetimes; application ACLs govern new requests and grants.
