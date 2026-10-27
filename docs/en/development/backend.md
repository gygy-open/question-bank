# Backend Conventions

The backend is Python 3.13 + FastAPI + SQLAlchemy (Async). These are the main conventions; please follow them when contributing code.

## Async First

**Always use `AsyncSession` and `await`** for database operations.

## SQLAlchemy 2.0 Syntax

```python
result = await db.execute(
    select(Question).where(Question.status == QuestionStatus.PUBLISHED)
)
questions = result.scalars().all()
```

## CRUD Pattern

For new data access, inherit from `app/crud/base.py:CRUDBase`:

```python
class CRUDQuestion(CRUDBase[Question, QuestionCreate, QuestionUpdate]):
    ...
```

## Type Hints

Type hints are mandatory (`typing.List`, `typing.Optional`, etc.).

## Dependency Management

Use `uv`:

```bash
uv add <package>
```

## Database Migrations

```bash
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

Migration scripts live in `backend/alembic/versions/` and currently use a dual baseline that works for both SQLite and MySQL.

## AI Integration

- To add an AI provider: implement the `AIProvider` interface in `app/services/ai_provider.py`.
- Document parsing / extraction: use `DocProcessor` in `app/services/doc_processor.py`.
- AI configuration is **database-driven** (`ai_providers` and `ai_models` tables), not environment variables.

## Configuration

- Static configuration: `app/core/config.py`.
- Dynamic business configuration: the `system_setting` table (hot-reloaded from the UI).

## Directory Overview

| Directory | Responsibility |
|------|------|
| `app/api/v1/endpoints/` | Route endpoints |
| `app/crud/` | Data access |
| `app/models/` | ORM models |
| `app/schemas/` | Pydantic models |
| `app/services/` | Business services |
| `scripts/` | Ops / data scripts |
