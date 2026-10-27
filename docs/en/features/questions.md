# Question Bank

The question bank provides search, editing, bulk operations, parent/child question structures, and soft deletion for questions.

::: tip Visibility and Permissions
Each question can be **Public** (shared within the subject) or **Private** (visible only to its creator; useful for original or in-progress adapted questions). Teachers can only see questions in subjects they are authorized for; whether they can create or edit questions depends on their subject role. See [Permissions & Roles](/en/admin/permissions).
:::

## Question Types

| Question Type | Identifier | Description |
|------|------|------|
| Single Choice | `single_choice` | One correct option |
| Multiple Choice | `multiple_choice` | Multiple correct options |
| True/False | `true_false` | True / False |
| Fill in the Blank | `fill_in_the_blank` | Supports **multiple blanks**, each with **multiple accepted answers** |
| Free Response | `free_response` | Subjective / short-answer questions |

Stems and explanations support rich text and **LaTeX formulas**.

## Filtering

The question list supports combining multiple filters:

- Subject, knowledge point, tags (multi-select)
- Question type, difficulty, status
- Import Task (by batch / batch name)
- Keyword (full-text search on the stem)
- Creator, reviewer, review count
- Source, top-level questions only (parent questions)

## Question Fields

- `content` stem (Markdown / HTML)
- `options` options (choice questions): `[{"label":"A","content":"..."}, ...]`
- `answer` reference answer (fill-in-the-blank uses a multi-answer structure, e.g. `[["a","A"],["b","B"]]`)
- `thinking` / `analysis` / `summary` approach / explanation / summary
- `difficulty` difficulty (1–5, default 1)
- `status` status (see [Review Workflow](/en/features/review-workflow))

## Bulk Operations

- **Bulk create**: write multiple questions at once (supports nested parent/child questions); Smart Import is built on this.
- **Bulk delete**: soft delete, with an activity log entry.
- **Bulk update**: change metadata such as source in bulk.

## Parent/Child Questions

- A parent question has an empty `parent_id` and can contain multiple child questions.
- Child questions link to their parent via `parent_id`.
- Deleting a parent question also deletes its child questions (cascade).
- Use cases: material questions with several sub-questions, question variants, sub-parts.

## Soft Deletion

- Deleting a question only sets a `deleted_at` timestamp; default queries exclude it automatically.
- An audit trail is kept, and deleted questions can be restored.

::: warning Difference from Permanent Deletion
Soft-deleted questions can be restored; to purge them permanently, an administrator must do so through operational means.
:::

## Relations

A question can be linked to: tags (many-to-many), knowledge points (many-to-many), an Import Task, its creator / last updater (audit), and review logs.
