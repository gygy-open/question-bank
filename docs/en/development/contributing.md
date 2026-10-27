# Contributing

Contributions are welcome! The full guide is [`CONTRIBUTING.md`](https://github.com/gygy-open/question-bank/blob/main/CONTRIBUTING.md) in the repository root; this page is a summary.

## License

This project is licensed under **AGPL-3.0-or-later**. By submitting a pull request, you agree to license your contribution under the same license.

## Branches and Commits

- Create a feature branch from `main`: `feat/xxx`, `fix/xxx`, `docs/xxx`.
- We recommend [Conventional Commits](https://www.conventionalcommits.org/) for commit messages:
  - `feat: add bulk question export API`
  - `fix: fix LaTeX rendering of fill-in-the-blank answers`
  - `docs: update deployment docs`

## Code Style

**Backend (Python)**

- Type hints are mandatory; database access uses `AsyncSession` + SQLAlchemy 2.0 syntax.
- New CRUD classes inherit from `app/crud/base.py:CRUDBase`.
- Add dependencies with `uv add <package>`; include an Alembic migration with any database change.

**Frontend (Vue/TS)**

- `<script setup lang="ts">`; prefer `ref`.
- Use `zod` + `vee-validate` for form validation.
- Tailwind v4 utility classes, no scoped CSS; use `lucide-vue-next` for icons.
- Make API calls through `useAPI`.

See [Backend Conventions](/en/development/backend) and [Frontend Conventions](/en/development/frontend) for details.

## Submitting a Pull Request

1. Fork the repository and create a feature branch.
2. Before submitting, make sure both frontend and backend start correctly locally.
3. Include Alembic migration files for any database change.
4. Include screenshots for any UI change.
5. Describe the motivation, approach and verification steps in the PR description.

## Reporting Issues

When opening an issue, please try to include: steps to reproduce, expected vs. actual behavior, environment details (OS, Python/Node version, browser), and relevant logs or screenshots.

## Security Issues

::: warning
Please **do not** report security vulnerabilities in public issues. Contact the maintainers privately by email instead.
:::

## Contributing to the Docs

This docs site is built with [VitePress](https://vitepress.dev/); its source is in `docs/`. To preview locally:

```bash
cd docs
pnpm install
pnpm docs:dev
```

After a push to `docs/**` on the `main` branch, GitHub Actions automatically builds and deploys the site to GitHub Pages.

### Docs Translations

Chinese is the single source; English translations live in `docs/en/`, mirroring the Chinese paths one-to-one (`guide/`, `desktop/`, `server/`, `admin/`, `features/`, `development/` and the home page). The repository `README.md` has an English counterpart, `README.en.md`, which is only checked for staleness, not structure, so the two may differ in content (e.g. the English one omits the WeChat section); mark it with the path `../README.md`.

- After changing a Chinese page, run `pnpm i18n:status` to list translations that are missing, stale, orphaned, or structurally inconsistent (structure).
- Update the matching page under `docs/en/`: the number of headings, code blocks, `:::` containers and images must match the source; prefix internal links with `/en`; use the app's actual English UI text for UI labels (see `frontend/i18n/locales/en-US.json`), and follow `frontend/i18n/glossary.json` for terminology.
- When a translation is done, run `pnpm i18n:mark <path>` (e.g. `pnpm i18n:mark guide/introduction.md`) to record the source hash, and commit `docs/.translation-lock.json`.
- `pnpm i18n:check` exits non-zero if there are any problems; the deploy workflow only prints the status and does not block a release because of stale translations.
- The sidebar and navigation are maintained in `.vitepress/locales/zh.mts` and `en.mts` respectively; when adding a page, add it to both.
- Browser language detection: on the first visit to a bilingual page, if the browser's preferred language is not Chinese, the visitor is redirected to the matching English page; after that, the last language the user viewed is remembered (switching via the language menu takes effect). The logic is in `.vitepress/lang-redirect.mts`, and its bilingual scope must stay in sync with `SCOPE` in `scripts/i18n-docs.mjs`.
