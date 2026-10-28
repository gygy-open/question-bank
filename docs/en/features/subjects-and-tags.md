# Subjects & Tags

Subjects and tags are the classification dimensions used to organize the question bank.

::: tip Management Permissions
Creating / editing / deleting **subjects** is limited to Super Administrators; creating, editing, and deleting **knowledge points / tags** requires the **Editor** role or higher in the subject; managing **tag categories** and bulk-importing tags requires the subject's **Manager** role; viewers can only view. See [Permissions & Roles](/en/admin/permissions).
:::

## Subjects

A subject is the top-level category of the question bank; questions and knowledge points all belong to a subject.

Fields: name, identifier (slug, unique), description, review threshold `required_review_count` (default 1).

Actions: create, edit, and delete subjects (Super Administrators only); each subject maintains its own [knowledge point system](/en/features/knowledge-points).

## Tags

Tags are a flexible classification dimension linked to questions **many-to-many**. Each tag has a name, a **category**, and a color.

**Built-in tag categories:**

| Category | Identifier | Examples |
|------|------|------|
| Year | `year` | 2023, 2024 |
| Source | `source` | A mock exam |
| Grade | `grade` | 高一、高二 (Grade 10, Grade 11) |
| Semester | `semester` | 上学期、下学期 (fall, spring semester) |
| Exam Type | `exam_type` | Midterm, final, mock |
| Feature | `feature` | Typical, final challenge question, in-sync practice |
| General | `general` | Default |

Actions: create (with automatic duplicate check), edit, delete (cascades to clean up links).

## Tag Categories (Management)

Tag categories define the available tag groups, with a name, slug (unique), sort order, and enabled status.

::: tip Permissions
**Managing tag categories is exclusive to Super Administrators**. Regular users can use tags in existing categories but cannot add or delete the categories themselves.
:::

Deleting a tag category also deletes the tags under it. Proceed with care.
