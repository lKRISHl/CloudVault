# CloudVault

**AI-Native, Multi-Tenant Cloud File Storage & Collaboration SaaS**

CloudVault bridges the gap between simple object storage and intelligent document management, providing teams with powerful search, summarization, and collaboration capabilities out-of-the-box.

## Key Features (Planned)
- 📂 Secure file and folder management
- 🤝 Granular sharing and access control
- 🤖 AI-powered document summarization
- 🔍 Semantic (RAG) search across your files
- 🏢 Strict multi-tenant data isolation

## Tech Stack
- **Frontend**: React, TypeScript, Vite, Tailwind CSS
- **Backend**: Python, FastAPI, SQLAlchemy
- **Data & Infra**: PostgreSQL, Redis, MinIO/S3, Docker

## Quick Start (Local Development)

1. Clone the repository
2. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
3. Start the infrastructure for running the backend and frontend directly:
   ```bash
   docker compose up -d postgres redis minio minio-setup
   ```
4. Backend:
   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements-dev.txt
   cp ../.env .env
   alembic upgrade head
   uvicorn app.main:app --reload
   ```
5. Frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

Alternatively, run the complete container stack with `docker compose up --build -d`
and open http://localhost:3000. The backend applies Alembic migrations before starting;
the frontend forwards `/api/v1` requests to the backend through Nginx.
The Compose stack uses development credentials and is not a production deployment.

## Verification

- Backend: `cd backend`, then `python -m pytest tests/ -v` and `ruff check .`.
- Frontend: `cd frontend`, then `npm test`, `npm run lint`, and `npm run build`.
- Local backend tests use a temporary SQLite file. For PostgreSQL tests, set
  `TEST_DATABASE_URL` to a **dedicated disposable database**: fixtures create and
  remove CloudVault tables. Never point this variable at an application database.
- GitHub Actions runs PostgreSQL-backed tests, migration upgrade/check/downgrade,
  and a Docker smoke test covering the frontend, API proxy, and registration.
- Production requires a custom `SECRET_KEY` of at least 32 bytes, generated with
  a cryptographically secure random generator; default development keys are rejected.

## Documentation
- [Architecture Details](ARCHITECTURE.md)
- [Development Plan](DEVELOPMENT_PLAN.md)
- [Agent Instructions](AGENTS.md)

## License
MIT License - Copyright (c) 2026 CloudVault Contributors
