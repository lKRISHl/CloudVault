# Contributing to CloudVault

## Development Setup
1. Clone the repository.
2. Copy `.env.example` to `.env` and fill in any required variables.
3. Run `docker-compose up -d` to start the infrastructure.
4. Set up the backend (Python venv, pip install) and frontend (npm install).

## Code Style
- **Python**: Use `ruff` for linting and formatting.
- **TypeScript**: Use `eslint` and `prettier`.

## Testing
- Tests must be written for all new features.
- Backend: Run `pytest`.
- Frontend: Run `vitest`.

## Commit Messages
Use conventional commits (e.g., `feat: add file upload`, `fix: correct typo in docs`).

## Pull Requests
Ensure all CI checks pass before requesting a review.
