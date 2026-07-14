# Question Bank Project Instructions

## Project Context
- **Backend**: Python 3.13+, FastAPI, SQLAlchemy (Async), Alembic, Pydantic.
- **Frontend**: Nuxt 4 (SPA mode), Vue 3.5+, TypeScript, Tailwind CSS v4, Shadcn UI.
- **AI**: Multi-provider (Gemini, OpenAI) via `AIProvider` interface.
- **Vector DB**: ChromaDB.
- **Infra**: Docker, Justfile, MySQL.

## Architecture & Patterns

### Backend (`backend/`)
- **Async First**: ALWAYS use `AsyncSession` and `await` for DB operations.
- **CRUD Pattern**: Inherit from `CRUDBase` in `app/crud/base.py`.
  - *Example*: `class CRUDQuestion(CRUDBase[Question, QuestionCreate, QuestionUpdate])`
- **AI Integration**:
  - Implement `AIProvider` in `app/services/ai_provider.py` for new providers.
  - Use `DocProcessor` in `app/services/doc_processor.py` for document parsing/extraction.
  - Configuration is DB-backed (`ai_providers`, `ai_models`), NOT env vars.
- **Settings**: Static config in `app/core/config.py`. Dynamic business config in `system_setting` table.

### Frontend (`frontend/`)
- **SPA Mode**: `ssr: false` is set in `nuxt.config.ts`.
- **API Layer**:
  - Use `useAPI` composable: `const { data } = await useAPI('/endpoint')`.
  - Auth headers are auto-injected by `app/plugins/api.ts`.
- **UI Components**: Located in `app/components/ui/`. Use `lucide-vue-next` for icons.
- **Rich Text/Math**: `tiptap` for editing, `katex` for rendering, `mathlive` for input.

## Critical Workflows

### Development
- **Frontend**: `pnpm dev` (Proxies `/api` to backend).
- **Backend**: `uv run fastapi dev app/main.py`.
- **Database Migrations**:
  - Create: `uv run alembic revision --autogenerate -m "message"`
  - Apply: `uv run alembic upgrade head`
- **Scripts**: Run utility scripts with `uv run python scripts/<script_name>.py`.

### Build & Deploy
- **Frontend**: `just build-and-push-frontend`
- **Backend**: `just build-and-push-backend`

## Coding Conventions

### Python
- **Type Hints**: MANDATORY (`typing.List`, `typing.Optional`).
- **SQLAlchemy**: Use 2.0 syntax: `select(Model).where(Model.field == value)`.
- **Dependencies**: Manage with `uv` (`uv add package`).

### Vue/TypeScript
- **Components**: Use `<script setup lang="ts">`.
- **State**: Prefer `ref` over `reactive`.
- **Validation**: Use `zod` schemas with `vee-validate`.
- **Styling**: Utility-first Tailwind v4. Avoid scoped CSS where possible.
- **Imports**: Use `@/` alias for `app/` root in frontend.

## Key Files
- `backend/app/services/ai_provider.py`: AI Provider interface.
- `backend/app/services/doc_processor.py`: Document processing logic.
- `backend/app/crud/base.py`: Generic CRUD repository.
- `frontend/app/plugins/api.ts`: API client config.
- `frontend/app/composables/useAPI.ts`: API hook.
