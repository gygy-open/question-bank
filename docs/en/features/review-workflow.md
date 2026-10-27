# Review Workflow

Questions go through a set of status transitions for quality control, with a complete review log.

## Status Transitions

```
草稿(draft) → 待审(pending) → 发布(published) → 归档(archived)
```

| Status | Identifier | Meaning |
|------|------|------|
| Draft | `draft` | Created, not yet submitted for review |
| Pending Review | `pending` | Submitted, awaiting review |
| Published | `published` | Approved and officially available |
| Archived | `archived` | No longer in use, kept for the record |

## Review Count and Threshold

- Each question has a `review_count` that increases with every review action.
- Each subject can set a `required_review_count` (default 1) as the minimum number of reviews before publishing.

The review threshold of a subject is configured in [Subjects & Tags](/en/features/subjects-and-tags).

## Review Log

- Every review action is recorded in the activity log (`action = review`), including the reviewer, time, and status change.
- Together with [Activity Logs](/en/features/activity-logs), the complete history can be traced.

## Permissions

- Super Administrators can review all content.
- Regular users perform the corresponding actions on their own content.

For details on roles and permissions, see [Users](/en/admin/users).
