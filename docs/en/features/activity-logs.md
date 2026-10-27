# Activity Logs

Activity Logs record key operations in the system for traceability and compliance.

## What Is Recorded

Each log entry contains:

| Field | Description |
|------|------|
| `user_id` | User who performed the action |
| `action` | Action type (create / update / delete / login / review, etc.) |
| `resource_type` | Resource type (question / knowledge_point / subject / tag / user, etc.) |
| `resource_id` | Resource ID |
| `details` | Change snapshot (JSON) |
| `ip_address` | Source IP of the request |
| `created_at` | Timestamp |

## Viewing

- Paginated browsing, filterable by user.
- The table shows ID, user, action, resource type, resource ID, IP, time, and details.

## Permissions

::: warning Super Administrators Only
The Activity Logs view is available only to **Super Administrators** (for viewing all logs). Regular users cannot access it.
:::

## Relation to the Review Workflow

Question review actions (`action = review`) are also written to the activity log; combined with the [Review Workflow](/en/features/review-workflow), you can trace each question's review history.
