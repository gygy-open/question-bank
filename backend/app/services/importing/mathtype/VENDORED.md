# Vendored: mathtypejx MTEF parser

- Upstream: https://github.com/a917470154/mathtypejx (MIT, see `LICENSE` / `NOTICE`)
- Commit: `7d90e7274c85cf56ac28d4d15e593044693d7e70`
- Copied: `src/mathtypejx/mtef/` only (MTEF v3/v5 → MathML). The OMML/docx-rewrite parts are not vendored.
- Fontmaps under `xslt/xsl/fontmaps/` keep their BSD-style license (`xslt/xsl/fontmaps/LICENSE`).
- Local change: the usage example in `__init__.py` docstring points to this package path.

## Updating

Run `just sync-mathtype` (latest upstream) or `just sync-mathtype <sha|tag>` from `backend/`.
It replaces the upstream files here, re-applies the local import-path patch, updates the commit
above, syncs `tests/fixtures/mathtype/*.bin`, shows the diff stat and runs the import tests.
Offline: `uv run python scripts/sync_mathtype.py --source <checkout> --sha <sha>`.
Don't edit upstream files here directly; a sync will overwrite them. If a fix is needed, add it to
`LOCAL_PATCHES` in `scripts/sync_mathtype.py` (or upstream it).
