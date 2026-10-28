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

## Duplicate Check

When you create or edit a question, it is compared with the **questions you can see in the same subject**. If a duplicate or highly similar question exists, you are asked to confirm before it is saved.

- **Formatting doesn't matter**: whitespace, line breaks, Chinese/English punctuation, full/half-width characters, question numbers (e.g. "1." or "(2)"), formula notation (e.g. `\dfrac` vs `\frac`) and option order are all ignored.
- **What is compared**: question type, stem, options, and the material of material sub-questions; answers and explanations are not compared.
- **Two levels**:
  - **Duplicate**: identical after normalization.
  - **Highly similar**: 90% similar or more (typos, a few missing words). Questions that differ only in numbers or formulas are marked "possibly a variant".
- **Hints while editing**: the editor shows possible duplicates at the top as you type; expand to view and open them.
- **Confirmation on save**: if a match is found on save, a comparison appears and you can choose "Save anyway" or cancel.
- Smart Import, MCP and the AI Assistant check for duplicates too; see [Smart Import](/en/features/import#duplicate-check) and [MCP Access](/en/features/mcp).

## Soft Deletion

- Deleting a question only sets a `deleted_at` timestamp; default queries exclude it automatically.
- An audit trail is kept, and deleted questions can be restored.

::: warning Difference from Permanent Deletion
Soft-deleted questions can be restored; to purge them permanently, an administrator must do so through operational means.
:::

## Relations

A question can be linked to: tags (many-to-many), knowledge points (many-to-many), an Import Task, its creator / last updater (audit), and review logs.
