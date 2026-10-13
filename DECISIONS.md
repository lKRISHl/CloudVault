# Architectural Decision Records

## ADR-001: Modular Monolith Architecture
- **Context**: Starting a new SaaS product with uncertain domain boundaries.
- **Decision**: Adopt a modular monolith architecture.
- **Rationale**: Reduces operational overhead and simplifies deployments while allowing for future microservice extraction if needed.
- **Alternatives considered**: Microservices (rejected due to premature optimization and overhead).

## ADR-002: Async SQLAlchemy with asyncpg
- **Context**: Need high-performance database access for a FastAPI application.
- **Decision**: Use SQLAlchemy with the asyncpg driver.
- **Rationale**: Maximizes concurrency and integrates cleanly with FastAPI's async nature.
- **Alternatives considered**: Synchronous SQLAlchemy, Tortoise ORM.

## ADR-003: Pydantic Settings for Configuration
- **Context**: Managing environment variables and configurations securely.
- **Decision**: Use `pydantic-settings`.
- **Rationale**: Provides strong typing and validation for environment variables out-of-the-box.
- **Alternatives considered**: os.environ, python-decouple.

## ADR-004: S3-Compatible Object Storage
- **Context**: Storing user files and assets securely and scalably.
- **Decision**: Use MinIO for local development and S3/R2 for production.
- **Rationale**: S3 API is the industry standard; MinIO provides an exact local replica.
- **Alternatives considered**: Storing files in DB (rejected due to performance/cost), local filesystem (rejected for scalability).

## ADR-006: JWT Access Tokens + Rotating Refresh Cookies
- **Context**: Phase 1 needs authentication for a browser SPA without placing long-lived secrets in JavaScript storage.
- **Decision**: Issue short-lived JWT access tokens in the JSON body and rotating refresh tokens in HttpOnly `SameSite=lax` cookies. Persist only SHA-256 hashes of refresh tokens.
- **Rationale**: Access tokens stay out of localStorage; refresh tokens can be revoked server-side; rotation invalidates stolen cookies after use.
- **Alternatives considered**: Server sessions in Redis only, JWT in localStorage, opaque access tokens.

## ADR-007: One Tenant Per User at Registration
- **Context**: CloudVault is multi-tenant; registration must create an isolated workspace.
- **Decision**: Registering creates a tenant plus the first user as `owner`. Users currently belong to a single tenant via `users.tenant_id`.
- **Rationale**: Delivers tenant isolation immediately without a membership join table. Organization membership is planned in Phase 2; resource permissions are planned in Phase 12.
- **Alternatives considered**: Global users with a memberships table from day one.

## ADR-005: PostgreSQL + pgvector for Vector Search
- **Context**: Needing vector storage for AI semantic search.
- **Decision**: Use PostgreSQL with the pgvector extension.
- **Rationale**: Keeps relational and vector data in the same datastore, simplifying operations and transactions.
- **Alternatives considered**: Pinecone, Milvus, Qdrant (rejected to reduce infrastructure complexity initially).

## ADR-008: Atomic Refresh Rotation and Shared Browser Refresh
- **Context**: Concurrent requests could read the same valid refresh token and issue multiple replacements.
- **Decision**: Claim refresh tokens using `UPDATE ... WHERE revoked_at IS NULL AND expires_at > now RETURNING id`; commit that update together with replacement insertion. Logout also uses a conditional update. Share one in-flight refresh promise within each frontend tab, including React StrictMode startup.
- **Rationale**: Enforces one successful rotation in shared database state across backend instances, without relying on process-local locks. Local concurrency tests use separate sessions against a temporary SQLite file; CI runs them against PostgreSQL.
- **Limitations**: Separate tabs do not share the frontend promise. Token-family revocation on replay is deferred to security hardening.

## ADR-009: Phase 0–1 Verification and Development Startup
- **Context**: The abbreviated development plan diverged from the master roadmap, and Docker frontend ports and proxy paths were inconsistent.
- **Decision**: Restore the full Phase 0–33 roadmap. Run development migrations before the Compose backend starts; serve frontend port 80 through host port 3000 and preserve `/api/v1` in proxy requests. Add PostgreSQL and Docker smoke verification to CI.
- **Limitations**: Development startup assumes one backend container. Production migration orchestration is deferred to deployment phases. Docker and PostgreSQL are unavailable on the current host, so CI checks remain unverified until run remotely.
