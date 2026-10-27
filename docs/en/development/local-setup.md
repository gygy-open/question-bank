# Local Development

How contributors set up a local development environment.

## Prerequisites

- Python 3.13+ (managed with [uv](https://github.com/astral-sh/uv))
- Node.js 20+ and [pnpm](https://pnpm.io/)
- MySQL 8.0 (or run it with Docker)
- Docker & Docker Compose (optional, to start dependencies in one step)

## Backend

```bash
cd backend

# Install dependencies
uv sync

# Apply database migrations
uv run alembic upgrade head

# Create a superuser (optional; you can also create one in the /setup wizard when you first open the frontend)
uv run python scripts/create_superuser.py

# Start the dev server (hot reload)
uv run fastapi dev app/main.py
```

The backend listens on `http://localhost:8000` by default, with API docs at `/docs`. After your first sign-in you are taken to an onboarding page to create your first subject.

## Frontend

```bash
cd frontend

# Install dependencies
pnpm install

# Start the dev server (proxies /api to the backend)
pnpm dev
```

The frontend dev server proxies `/api` to the backend, so no extra CORS configuration is needed.

## Docs Site (This Repository)

```bash
cd docs
pnpm install
pnpm docs:dev
```

## Common Commands

| Task | Command |
|------|------|
| Add a backend dependency | `uv add <package>` |
| Generate a migration | `uv run alembic revision --autogenerate -m "msg"` |
| Apply migrations | `uv run alembic upgrade head` |
| Run a script | `uv run python scripts/<script>.py` |
| Build the frontend (for desktop packaging) | `pnpm generate` |

For more conventions, see [Backend Conventions](/en/development/backend) and [Frontend Conventions](/en/development/frontend).
