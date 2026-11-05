# QuestionBank Project Instructions

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
  - Router aggregated in `app/api/v1/api.py`; route modules in `app/api/v1/endpoints/` (e.g. `questions`, `chat`, `import_tasks`, `papers`, `knowledge_points`, `ai_config`, `subjects`, `tags`, `users`, `login`, `setup`, `upload`, `system`, `dashboard`, `api_keys`, `structure`).
  - Shared dependencies (auth, DB session) in `app/api/deps.py`.
- **Models**: SQLAlchemy models in `app/models/` (`question`, `subject`, `tag`, `tag_category`, `knowledge_point`, `chat`, `import_task`, `ai_config`, `activity_log`, `prompt`, `system_setting`, `user`); shared base in `app/models/base.py`.
- **Services** (`app/services/`):
  - `ai_provider.py`: Implement the `AIProvider` interface here for new AI providers. Config is DB-backed (`ai_providers`, `ai_models` tables), NOT env vars.
  - `doc_processor.py`: Document parsing/extraction. `structured_parser.py`: structured content parsing. `pandoc.py`: document conversion.
  - `embedding.py`: Vector embeddings (ChromaDB). `question_service.py`: question domain logic. `paper_generator.py`: paper generation.
  - `activity_logger.py`: activity logging. `dashboard_service.py`: dashboard aggregate stats (reuse `visible_questions_filter`). `tools.py`: shared utilities.
- **Question dedup** (`app/services/question_dedup*.py`, spec `docs/specs/question-dedup.md`): signatures (`questions.dedup_*`, `question_dedup_bands`) are maintained by SQLAlchemy flush hooks, so every write path is covered. `question.create/update/derived.create/batch_create` raise 409 `question.duplicate_suspected` unless `allow_duplicate=True` (field is `exclude=True`, never persisted); paper import uses `allow_duplicate_temp_ids`. Bump `DEDUP_VERSION` when normalization changes (triggers backfill).
- **Background jobs** (`app/models/job.py`, `app/services/jobs/`): every background task is a row in `jobs` (execution state only: pending/running/paused/succeeded/failed/cancelled, priority USER > AUTO > BACKFILL). The worker only claims jobs and dispatches by `type` to a `JobHandler` registered with `@register_handler` (add the module to `_HANDLER_MODULES`). Handlers report via `JobContext` (`set_progress`/`succeed`/`fail`/`pause`/`handle_ai_error`); AI errors go through `app/services/ai_errors.py` (transient → retry; provider → pause every queued job on the same provider; document → fail) and the worker must never exit on AI errors. `JobHandler.project()` mirrors execution state onto the business table in the same transaction. Business tables keep business state and link via `jobs.target_type/target_id`.
- **Import queue** (`app/services/import_task_service.py`, `app/services/importing/job.py`, UI `/imports`): every import (file, image, pasted text) is an `ImportTask` plus an `import.extract` job; the task's status/paused_reason/provider_id/error_message/progress are the job's projection (only written via `job_service`). Results are stored as JSON (`result_sha256`) and left in `review_ready`; the review UI commits via `paper-imports` with `import_task_id` (no new task). `auto_commit` tasks save directly. The `/upload/*` sync endpoints are deprecated.
- **Question structure** (`app/services/structure/`, `app/capabilities/structure.py`, `app/api/v1/endpoints/structure.py`, spec `docs/specs/question-structure.md`, ADR `docs/specs/adr-question-element-model.md`): the stem (never the answer) is decomposed into conditions and asks, each classified by a per-subject structure type tree (`struct_types`; roots auto-created by `types.ensure_roots`). Each decomposition is a snapshot (`struct_runs` → `struct_elements`/`struct_asks`/`struct_ask_elements`) with `stem_text` (math kept as `$...$`) that all spans refer to; at most one `accepted` and one `draft` per target; outdated when `source_revision` ≠ the question's `content_revision`. AI runs as `structure.decompose` jobs, results are checked by `check.py` and saved as drafts for review. Switches: system setting `structure.enabled`, subject setting `structure.auto_decompose` (default off; hooks after question create/import/approve via `after_questions_saved`). Bump `decompose.PROMPT_VERSION` when changing `AI_STRUCT_DECOMPOSE_PROMPT`.
- **Structure, later phases** (same spec §12): `struct_elements.content_sig` (dedup normalization) powers similar-question `mode=elements`; `origin=agent` marks MCP saves. Induction (`induce.py`, `struct_type.induce` job → `struct_type_candidates`, teacher accepts/merges/ignores and `type_id` is backfilled in place). Parameter slots (`struct_params`, span-based, inherited by human saves; `params.py` checks) drive `structure.variant` jobs (`variant.py`: replace by span via `textmap.py`, never string replace → AI verify + `guard_verdict` → draft via `question.derived.create` with relation `variant_of`; only exact duplicates are blocked). Element groups (`struct_element_groups`) and the composition basket use `structure.compose` jobs (`compose.py`: AI writes → re-decompose + `consistency_problems` → verify → draft, relations `variant_of` / `composed_from`). Solution structure (`solution.py`, `solution_runs`/`solution_steps`/`solution_step_links`/`solution_misconceptions`, `solution.decompose` job) needs an accepted stem run; method types (`kind=method`, `struct_types.weight`) give `questions.thinking_difficulty` (min over accepted solutions, recomputed on accept / weight change). `struct_type_knowledge_points` maps types to knowledge points for suggestions. Question relations are typed (`QuestionRelationType`). Learning analytics (N6) is not built.
- **MCP** (`app/mcp_server/`): MCP server mounted at `/api/mcp` (same port as the API; nginx proxies it in Docker). Auth via per-user API keys (`qb_` prefix, `api_keys` table, managed in Settings → MCP access); keys inherit the owner's permissions and are MCP-only. Every exposed capability is auto-mapped to a tool (`question.create` → `question_create`) — register its output type in `CAPABILITY_OUTPUT_TYPES` (`tools.py`) or add it to `EXCLUDED_CAPABILITIES`. Master switch: system setting `mcp.enabled`. Media uploads use presigned URLs (`create_media_upload_url` tool → `POST /api/mcp/uploads/{token}`, `app/mcp_server/uploads.py`) because the model running curl cannot see the API key. Model-facing text (tool descriptions, schemas, instructions) is English-only and not translated.
- **Settings**: Static config in `app/core/config.py`. Dynamic business config in the `system_setting` table.

### Desktop App (`backend/`)
- **Launcher**: `run.py` is the unified entrypoint with two roles:
  - `tray` (default for packaged builds): runs everything in-process behind a notification-area icon (`app/tray.py`); opens a native window via `pywebview`, falling back to the default browser.
  - `server`: runs migrations + background worker + uvicorn in the foreground (dev and Docker).
  - Force a role with `--tray` / `--server` or `QB_ROLE=tray|server`.
- **Worker**: `app/worker.py` claims `jobs` by priority and dispatches them to handlers (imports, stem decomposition).
- **Packaging**: `run.spec` builds with PyInstaller (bundles the generated SPA; runs migrations + API + worker): a single-file `.exe` on Windows (Inno Setup installer in `deploy/windows/`), a `.app` bundle on macOS (signed/DMG via `deploy/macos/package.sh`; Dock integration in `app/macos_dock.py`). Must be built on the target OS.

### Frontend (`frontend/`)
- **SPA Mode**: `ssr: false` is set in `nuxt.config.ts`. Static output via `pnpm generate` (bundled into the desktop build).
- **API Layer**:
  - Use the `useAPI` composable: `const { data } = await useAPI('/endpoint')`.
  - Auth headers are auto-injected by `app/plugins/api.ts`.
- **Composables** (`app/composables/`): `useAPI`, `useAuth`, `useChatState`, `usePaperBasket`, `useUpdateCheck`, `useStructure` (+ `useStructureEnabled` for the global switch).
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
- **Desktop executable**: `just package` (runs `build-frontend`, then `pyinstaller run.spec --clean`). macOS DMG: `just package-macos`. CI: `.github/workflows/desktop-build.yml` (Windows + macOS arm64/x86_64).

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
- **i18n** (`@nuxtjs/i18n`, `no_prefix` strategy):
  - Locale files: `frontend/i18n/locales/{zh-CN,en-US}.json`. `zh-CN` is the single source of truth and fallback. **Only edit `zh-CN.json` by hand**; other locales are maintained by the translation workflow below.
  - Translation workflow (run in `frontend/`):
    1. Add/change keys in `zh-CN.json`, then `pnpm i18n:sync` — rebuilds other locales in zh-CN key order, prunes removed keys, and exports missing/stale entries to `i18n/.pending/<locale>.json` (staleness is tracked by source hashes in `i18n/.translation-lock.json`, which must be committed).
    2. Delegate to the `翻译` agent (`.github/agents/translator.agent.md`) per locale; it only writes `i18n/.pending/<locale>.out.json`, following `i18n/glossary.json`.
    3. `pnpm i18n:apply` — validates (keys, `{placeholders}`, vue-i18n syntax, no leftover Chinese) and merges; rejected entries stay pending for another round.
    4. `pnpm i18n:check` must pass (also enforced by `app/lib/__tests__/i18n.test.ts`).
    - Parallel batches: each worker writes new zh-CN keys to its own `i18n/.fragments/<batch>.json` instead of editing `zh-CN.json`; then `pnpm i18n:merge` merges them (aborts without writing on conflicting values) before step 1's sync.
  - New UI text MUST NOT be hardcoded: use `const { t } = useI18n()` / `t('ns.key')` (or `$t` in templates). Group keys by feature (`nav.*`, `auth.login.*`, ...).
  - Because pages are kept alive, never cache translated strings in module scope or plain `const`; use `t()` in templates or inside `computed` (e.g. zod schemas: `computed(() => toTypedSchema(...))`; option lists: `computed(() => [{ label: t('...'), value }])`).
  - Outside component setup (composables after `await`, `lib/` helpers) use `translate(key, params)` from `@/lib/locale`.
  - Rich text with inline markup: use `<i18n-t keypath="...">` with named slots (see `LanShareDialog.vue`).
  - Counts: no vue-i18n plural syntax; phrase messages so they read correctly for any number (e.g. `已选 {count} 个` → `Selected: {count}`).
  - Never translate "content language" (values sent to the backend, enum values, text that ends up in exported papers/question data, parser constants) — only display labels.
  - Dates/numbers: use `formatRelativeTime` (`@/lib/utils`) and `formatDateTime` / `formatDate` / `formatNumber` (`@/lib/locale`) instead of bare `toLocaleString()`.
  - Escape `@` and `|` in messages as `{'@'}` / `{'|'}` (vue-i18n syntax).

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
