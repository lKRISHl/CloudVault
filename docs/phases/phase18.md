# Phase 18 — Realtime

Implemented in source on 2026-10-16. Local core acceptance passed at the combined18+19 checkpoint2026-10-17 after
the user explicitly requested19 ahead of18A. Initial execution was deferred under the
two-phase cadence. Backend transport/authority and actual Redis
checks, frontend lint/build/unit tests and browser acceptance are recorded in the Phase19
report/CONTINUE, including initial failures and isolated reruns. Actual nginx/own receipt/
logout revocation smoke and two real-Redis browser reconnect/cross-tab cases pass. No realtime
migration is added; Phase19 adds021. Phase17/c3cf0ee CI fix are committed;18 is uncommitted.

## What was built and why

Authenticated WebSockets notify the browser when subscribed authorized views change:
folder/file pages, original and replacement upload receipts, scan state, version history,
preview jobs, search, trash, workspace membership, permissions and links. Clients refetch
through existing REST authorization; socket messages grant no file access. Generic change
notices are ephemeral. Receipt progress counts confirmed parts, not browser bytes in flight.

The server observes committed database state through existing service authorization.
This includes worker changes without adding publication hooks to every writer. It hashes
bounded authorized pages internally, emitting only subscription keys, change/unavailable
reasons and the requester's visible pending-transfer IDs/confirmed-byte counts. Filenames,
private hashes, object keys, credentials and presigned grants are not sent over this feed.
The internal snapshot hash is not transmitted. Transitions between observations coalesce:
this is current-state refresh, not a durable activity stream or replay log (ADR-042).

## Request flow and authority

1. A verified bearer-authenticated user requests POST /api/v1/realtime/ticket. The API
   issues a random 20-second one-use Redis ticket bound to user, selected tenant and
   login session. A verified account without a tenant can observe only its workspace list.
2. The browser opens /api/v1/realtime/connect with an exact allowed Origin and no query
   parameters. It sends the ticket in its first frame within five seconds. No JWT or ticket
   enters URLs/subprotocol headers. Redis GETDEL prevents concurrent ticket replay.
3. Each observation rechecks session, verification, membership and resource access.
   A five-minute capability forces renewal with a fresh ticket. Invalid sessions prompt
   shared-cookie adoption; ordinary capability expiry reconnects.
4. At most eight subscribed views use paged REST-equivalent services. Each observation
   ends its read transaction before sending to slow sockets. No S3/native rendering work
   executes here. New subscriptions receive an authorized baseline.
5. Reconnect invalidates active protected REST queries. Lost heartbeats trigger jittered
   bounded retry; disconnected/overflow views use a 15-second REST refresh fallback.

Resource denial clears scoped caches and remounts protected page state, including preview
blob cleanup. Role changes refresh the actor. Search observation skips the normal search
request counter only through an internal service argument; socket budgets still apply.
Public schemas cannot enable that argument. Foreign/private-resource failures produce the
same unavailable signal. REST/download/scan checks remain authoritative. Already received
bytes and outstanding signed capabilities retain D01/D02 boundaries.

## Cross-tab session coordination (L15)

Refresh and cookie-changing actions acquire one same-origin Web Lock. BroadcastChannel and
storage events carry only version/sender/nonce/changing-or-changed signals, never tokens,
profiles or tenant IDs. Other tabs immediately fence responses, clear scoped state and
restore the shared cookie under the lock. Epoch/generation checks prevent old responses
from overwriting newer sessions. Automatic refresh compares subject, tenant and login-session
claims before request retry; it cannot replay a mutation under another identity/session.
Interrupted cookie actions reconcile after releasing the lock rather than replaying actions.

Without Web Locks, server-side single-use rotation remains authoritative, but competing
unsupported tabs may fail closed and require sign-in. Blocked channels/storage have safe
fallbacks, not an invented atomic localStorage lock. The supported browser/privacy matrix
still requires acceptance and deployment review (L40).

## Bounds and important files

- backend/app/api/realtime.py: thin ticket/socket routes and dependency lifecycle.
- backend/app/services/realtime.py: handshake, fresh authority, observation and cleanup.
- backend/app/services/realtime_store.py: opaque tickets and atomic Redis leases.
- backend/app/services/live_snapshots.py: authorized observations and own receipts.
- backend/app/schemas/realtime.py: strict topic/command validation.
- frontend/src/realtime/: shared subscriptions, invalidation, reconnect and safe notices.
- frontend/src/auth/sessionCoordination.ts and AuthContext.tsx: session ownership/fencing.
- frontend/src/services/api.ts: locked refresh, identity binding and preview wakeups.
- nginx/Vite/Compose: WebSocket forwarding and bounded ASGI frame queues.

Defaults: three-second observation (configurable 2–10), four sockets/user, 64/IP, 64/API
process. Redis leases last30s and renew each observation; keys expire after45s. Handshake
limit120/IP/minute; ticket category120/identity and1200/IP per configured account window.
Eight topics, 60 commands/minute, 8 KiB inbound frames, ASGI queue2. First-frame timeout5s,
send timeout2s, observation timeout10s. Retry backoff1–30s plus jitter; a healthy heartbeat
period resets it. Resource pages use25; search retains maximum100/offset10000. These are
bounds, not measured capacity. Per-IP identity is the ASGI peer; production proxy topology
needs review. Redis outage fails ticket/socket work closed; REST remains available. Redis
Cluster is not certified: the two-key lease script targets the current standalone deployment.

## Acceptance scope

Backend test_realtime.py covers verified tickets, Origin/query rejection, replay, session
expiry/revocation, tenant/private-resource observations, reconnect baselines, strict schemas,
command/frame limits and cleanup. test_realtime_redis.py has explicit TEST_REDIS_URL opt-in
cases for actual GETDEL concurrency and lease ownership/expiry. It deletes only its generated
keys, never flushes a shared database.

Frontend Realtime.test.tsx and SessionCoordination.test.ts cover subscription routing,
overflow, ticket placement, invalidation, denied scope, lost heartbeats, locks and secret-free
signals. WorkspaceSafety.test.ts adds same-workspace subject/session-change retry denial.
e2e/realtime.pw.ts authors shared-cookie workspace/concurrent-reload and offline-change
journeys; it needs explicit test Redis and the existing disposable application stack.

At the user-directed18+19 checkpoint run lint/type/build and frontend/backend regressions, then actual
PostgreSQL/Redis/provider/browser checks sequentially. Add/complete live cases for logout,
member removal, ACL revocation/private ancestors, rapid switches, scan/preview worker changes,
original/version receipt counts, connection caps/Redis restart, stalled clients, actual nginx
upgrade and REST fallback. Authored cases do not prove these behaviors. Preserve app data,
use disposable fixtures and record outcomes/fixes before marking either phase locally complete.
Remote CI still requires separately authorized push/dispatch.

## Limitations requiring explicit work

- **L15:** local core implementation/acceptance passes at18+19. Phase27 still
  owns refresh-family/replay and broader session-security verification.
- **L40 (new):** bounded observations coalesce transitions, lack durable replay/inbox and
  increase DB reads per socket/topic. Phase20 decides whether durable user notifications
  are required; implement/test them if included. Phase26 verifies proxy, broker restart,
  multi-process leases and browser/privacy failure behavior; 27 reviews ticket/Origin/proxy/
  refresh abuse; 28 implements connection/fallback/lease/observation alerts; 32 measures
  fanout, tenant fairness, latency and DB load and implements necessary admission/fanout
  changes. No production throughput or universal browser-support claim is made.
- **Inherited:** L10–L14/P01–P03 are due18A; L19/L04/L39 quota work19; L21/L36 retention20.
  L20/L22/L23/L25/L37/L38/L39 keep AWS/deployment/recovery26/31, security27, monitoring28
  and representative load32. L24 MFA remains27; L01 remote CI needs authorized push/dispatch.
  D01–D08 stay explicit. Consult the shared register for complete ownership/acceptance.

## Design discussion

Why observation rather than Redis resource events? It detects committed visible current
state from all writers without an outbox migration or trusting a lossy publisher. The cost
is repeated authorized reads and coalesced history, requiring measured production review.
Why REST refetch? A socket change is a hint; current access/quarantine checks must still
decide which metadata, derivative or download capability may be returned. Why a first-frame
ticket? Browser sockets cannot set arbitrary bearer headers; consuming a short-lived ticket
avoids placing long-lived JWTs in URLs/logs.
