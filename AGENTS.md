## Project
CloudVault — AI-Native, Multi-Tenant Cloud File Storage & Collaboration SaaS

## Architecture
Modular monolith with separated concerns:
- `backend/` — Python/FastAPI REST API
- `frontend/` — React/TypeScript/Vite SPA
- `workers/` — Celery background workers (future)
- `ai/` — AI/ML processing pipeline (future)
- `infra/` — Docker, monitoring, deployment configs

## Stack
- **Frontend**: React, TypeScript, Vite, Tailwind CSS, TanStack Query
- **Backend**: Python, FastAPI, Pydantic, SQLAlchemy (async), Alembic
- **Database**: PostgreSQL with pgvector (future)
- **Cache/Queue**: Redis, Celery
- **Storage**: S3-compatible (MinIO local, S3/R2 production)
- **AI**: Python-based pipeline (extraction, embeddings, RAG)
- **Realtime**: WebSockets
- **Testing**: pytest, Vitest, Playwright
- **Observability**: OpenTelemetry, Prometheus, Grafana
- **Deployment**: Docker, GitHub Actions

## Key Files
- `CONTINUE.md` — Current project state and next steps
- `PROJECT_CONTEXT.md` — Product vision and context
- `ARCHITECTURE.md` — System architecture details
- `DEVELOPMENT_PLAN.md` — Phase roadmap
- `DECISIONS.md` — Architectural decision log
- `CHANGELOG.md` — Version history
- `SECURITY.md` — Security considerations

## Development Rules
1. Read CONTINUE.md before any work
2. Inspect git status and existing code before changes
3. Do not store file bytes in PostgreSQL
4. Use presigned URLs for large file transfers
5. Enforce tenant isolation on every protected resource
6. Use service layer pattern — no business logic in route handlers
7. Write tests for every feature
8. Do not fabricate benchmarks or fake implementations
9. Document architectural decisions in DECISIONS.md

## Testing
- Backend: `cd backend && python -m pytest tests/ -v`
- Frontend: `cd frontend && npm test`
- Lint backend: `cd backend && ruff check .`
- Lint frontend: `cd frontend && npm run lint`
