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
3. Start the infrastructure:
   ```bash
   docker-compose up -d
   ```
4. Backend:
   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements-dev.txt
   alembic upgrade head
   uvicorn app.main:app --reload
   ```
5. Frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Documentation
- [Architecture Details](ARCHITECTURE.md)
- [Development Plan](DEVELOPMENT_PLAN.md)
- [Agent Instructions](AGENTS.md)

## License
MIT License - Copyright (c) 2026 CloudVault Contributors
