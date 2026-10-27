# Knowledge Points

The knowledge point system is a **tree-shaped knowledge structure** organized by subject. It is used to tag questions with knowledge points and powers AI knowledge point recommendations (RAG).

## Structure

- **Tree**: parent/child levels are built via `parent_id`, with unlimited nesting.
- **Per subject**: each knowledge point belongs to a subject.
- **Unique identifier**: the `(subject_id, slug)` combination is unique; the slug is a URL-friendly identifier.

Fields: name `name`, identifier `slug`, parent node `parent_id`, subject `subject_id`, creator / updater.

## Management

- View the full knowledge point tree of a subject
- Create root or child nodes
- Rename / change the slug
- Delete (cascades to child nodes)

::: warning Cascade Deletion
Deleting a knowledge point **also deletes all of its child nodes**. Proceed with care.
:::

## Linking to Questions

Questions and knowledge points have a **many-to-many** relationship: a question can be linked to one or more knowledge points, and knowledge points can be used as question bank filters.

## Vectorization and RAG

Knowledge points are **vectorized and written to ChromaDB** for semantic search:

- In the [AI Assistant](/en/features/chat), the AI can retrieve related knowledge points / questions as context.
- During Smart Import, the AI can map recommended knowledge points to your standard system.

After you change the **Embedding model** (`AI_EMBEDDING_MODEL_ID`) in [System Settings](/en/admin/system-settings), vectors for existing knowledge points are **not rebuilt automatically**. A "Rebuild Vector Index" prompt then appears at the top of the knowledge point tree; click it to re-vectorize with the new model.

::: tip Embedding Model Required
RAG relies on an Embedding model. Add and activate a model for vectorization in [AI Providers & Models](/en/admin/ai-config).
:::

::: tip Deferred Vectorization
When no Embedding model is configured, creating / editing knowledge points **does not trigger vector updates** (and does not raise an error). Once you have configured a model, click **Rebuild Vector Index** in the knowledge point tree to catch up in one go.
:::

## Batch Import

Administrators can **download an Excel template** from the knowledge point tree, fill it in, and **batch import** it — no command line needed.

### Steps

1. Open the knowledge point management page and select the target subject.
2. Click **Batch Import** → in the dialog, click **Download Excel Template**.
3. Fill in the template: `Subject Name` (required), `Level 1` (required), `Level 2`–`Level 8` (optional). Each row forms a parent/child chain from left to right; empty intermediate levels are skipped automatically.
4. Upload the completed `.xlsx` file (≤ 5MB), choose an import mode, and confirm.

### Import Modes

| Mode | Behavior | Effect on Question Links |
|------|------|------------------|
| **Incremental Add** (recommended) | Existing knowledge points (same subject, parent, and name) are skipped; only new nodes are created | ✅ Existing questions keep their knowledge point links |
| **Clear and Rebuild** | First deletes **all** knowledge points of the subjects in the file, then imports | ⚠️ Linked questions lose their knowledge point tags (the questions themselves are kept); you must type the subject name to confirm |

::: tip Idempotency
**Incremental Add** can safely import the same file multiple times: duplicate nodes are skipped and no duplicate data is created.
:::

::: warning Clear and Rebuild Cannot Be Undone
Clear and Rebuild cascades to child nodes and removes question links. Before you proceed, the dialog shows how many knowledge points and questions will be affected — confirm with care.
:::

After the import finishes, new knowledge points are vectorized automatically if an Embedding model is configured; otherwise, click **Rebuild Vector Index** in the knowledge point tree later to catch up.

### Command-Line Scripts (Optional)

The repository still includes scripts for bulk operations on the development / deployment side: `scripts/import_math_knowledge_points.py` and `scripts/sync_knowledge_points.py`. On the server edition, run them with `docker compose exec backend uv run python scripts/<script_name>.py`.
