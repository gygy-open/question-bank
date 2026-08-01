# Question Bank Project Instructions

## Project Context
- **Backend**: Python 3.13+, FastAPI, SQLAlchemy (Async), Alembic, Pydantic.
- **Frontend**: Nuxt 4 (SPA mode), Vue 3.5+, TypeScript, Tailwind CSS v4, Shadcn UI.
- **AI**: Multi-provider (Gemini via `google-genai`, OpenAI) through the `AIProvider` interface.
- **Vector DB**: ChromaDB (embeddings via `app/services/embedding.py`).
- **Infra**: Docker, `just` (Justfile), MySQL 8.0 (`mysql+aiomysql`).
- **Delivery**: Runs both as a web app (Docker) AND as a packaged single-file **desktop app** (PyInstaller + system tray).

## Architecture & Patterns

### Backend (`backend/`)
- **Async First**: ALWAYS use `AsyncSession` and `await` for DB operations.
- **CRUD Pattern**: Inherit from `CRUDBase` in `app/crud/base.py`.
  - *Example*: `class CRUDQuestion(CRUDBase[Question, QuestionCreate, QuestionUpdate])`
- **API Layer**: Versioned under `app/api/v1/`.
  - Router aggregated in `app/api/v1/api.py`; route modules in `app/api/v1/endpoints/` (e.g. `questions`, `chat`, `import_tasks`, `papers`, `knowledge_points`, `ai_config`, `subjects`, `tags`, `users`, `login`, `setup`, `upload`, `system`).
  - Shared dependencies (auth, DB session) in `app/api/deps.py`.
- **Models**: SQLAlchemy models in `app/models/` (`question`, `subject`, `tag`, `tag_category`, `knowledge_point`, `chat`, `import_task`, `ai_config`, `activity_log`, `prompt`, `system_setting`, `user`); shared base in `app/models/base.py`.
- **Services** (`app/services/`):
  - `ai_provider.py`: Implement the `AIProvider` interface here for new AI providers. Config is DB-backed (`ai_providers`, `ai_models` tables), NOT env vars.
  - `doc_processor.py`: Document parsing/extraction. `structured_parser.py`: structured content parsing. `pandoc.py`: document conversion.
  - `embedding.py`: Vector embeddings (ChromaDB). `question_service.py`: question domain logic. `paper_generator.py`: paper generation.
  - `activity_logger.py`: activity logging. `tools.py`: shared utilities.
- **Settings**: Static config in `app/core/config.py`. Dynamic business config in the `system_setting` table.

### Desktop App (`backend/`)
- **Launcher**: `run.py` is the unified entrypoint with two roles:
  - `tray` (default for packaged builds): runs everything in-process behind a notification-area icon (`app/tray.py`); opens a native window via `pywebview`, falling back to the default browser.
  - `server`: runs migrations + background worker + uvicorn in the foreground (dev and Docker).
  - Force a role with `--tray` / `--server` or `QB_ROLE=tray|server`.
- **Worker**: `app/worker.py` runs background jobs (e.g. imports).
- **Packaging**: `run.spec` builds a single-file executable with PyInstaller that bundles the generated SPA and runs migrations + API + worker.

### Frontend (`frontend/`)
- **SPA Mode**: `ssr: false` is set in `nuxt.config.ts`. Static output via `pnpm generate` (bundled into the desktop build).
- **API Layer**:
  - Use the `useAPI` composable: `const { data } = await useAPI('/endpoint')`.
  - Auth headers are auto-injected by `app/plugins/api.ts`.
- **Composables** (`app/composables/`): `useAPI`, `useAuth`, `useChatState`, `usePaperBasket`, `useUpdateCheck`.
- **App structure** (`app/`): `pages/` (Nuxt file-based routing), `layouts/`, `middleware/`, `components/`, `composables/`, `plugins/`, `extensions/` (tiptap), `lib/`, `assets/`, `types/` (shared TS types).
- **Components**: `app/components/ui/` (Shadcn primitives) and `app/components/manager/` (domain/admin components). Use `lucide-vue-next` for icons.
- **Rich Text/Math**: `tiptap` for editing, `katex` for rendering, `mathlive` for input.

## Critical Workflows

### Development
- **Frontend**: `pnpm dev` (proxies `/api` to backend).
- **Backend (web/dev)**: `uv run fastapi dev app/main.py`.
- **Backend (desktop/dev)**: `just run-desktop` (migrations + worker + API + opens UI) or `uv run python run.py`.
- **Database Migrations** (run from `backend/`):
  - Create: `just make_migration "message"` (→ `uv run alembic revision --autogenerate -m "message"`)
  - Apply: `just migrate` (→ `alembic upgrade head`)
  - Archived MySQL migration history lives in `alembic/versions_archive_mysql/`.
- **Scripts**: Run utility scripts with `uv run python scripts/<script_name>.py`.

### Build & Package
- **Frontend SPA**: `just build-frontend` (`cd ../frontend && pnpm install && pnpm generate`).
- **Desktop executable**: `just package` (runs `build-frontend`, then `pyinstaller run.spec --clean`).

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
- `backend/run.py`: Unified desktop/server launcher (tray/server roles).
- `backend/app/worker.py`: Background job worker.
- `backend/app/tray.py`: System-tray desktop shell.
- `backend/run.spec`: PyInstaller desktop packaging spec.
- `backend/justfile`: Migration, build, and packaging recipes.
- `backend/app/services/ai_provider.py`: AI Provider interface.
- `backend/app/services/doc_processor.py`: Document processing logic.
- `backend/app/crud/base.py`: Generic CRUD repository.
- `backend/app/api/deps.py`: Shared API dependencies (auth, DB session).
- `frontend/app/plugins/api.ts`: API client config.
- `frontend/app/composables/useAPI.ts`: API hook.
