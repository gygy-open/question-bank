# Permissions & Roles

The system uses a **two-level permission model**: a global Super Administrator, plus scoped roles granted per **subject**. For non-administrators, all access comes from subject membership — a user who hasn't been granted any subject can't see any question bank content.

## Two-Level Model

### Level 1 · Global Role

- **Super Administrator** (`is_superuser`): not restricted by any subject or visibility rule. Can manage users, system settings, AI configuration, and all content in every subject. Only Super Administrators can create / edit / delete **subjects** themselves.

### Level 2 · Subject-Scoped Roles

Granted to teachers subject by subject under **Subjects → Manage Members**:

| Role | Description |
|------|------|
| **Viewer** | Can only view the subject's questions, knowledge points, and tags; cannot make changes |
| **Editor** | Can create / edit / delete questions, knowledge points and tags in the subject |
| **Manager** | Everything an Editor can do, plus manage the subject's **members** and tag categories, and bulk-import tags |

A teacher can be granted **multiple subjects**, with a different role in each.

## Capability Matrix

| Capability | Super Administrator | Manager | Editor | Viewer |
|------|:---------:|:---------:|:-----:|:----:|
| View the subject's questions / knowledge points / tags | ✅ All subjects | ✅ Own subject | ✅ Own subject | ✅ Own subject |
| Create / edit questions | ✅ | ✅ | ✅ | ❌ |
| Create / edit / delete knowledge points and tags | ✅ | ✅ Own subject | ✅ Own subject | ❌ |
| Manage tag categories / bulk-import tags | ✅ | ✅ Own subject | ❌ | ❌ |
| Manage subject members (assign roles) | ✅ | ✅ Own subject | ❌ | ❌ |
| Create / edit / delete **subjects** | ✅ | ❌ | ❌ | ❌ |
| Rebuild knowledge point vectors / import | ✅ | ❌ | ❌ | ❌ |
| Users / system settings / AI configuration / audit logs | ✅ | ❌ | ❌ | ❌ |

> Subjects a user hasn't been granted are completely invisible to them — they don't appear in lists, search, exports, or even AI Assistant retrieval.

## Assigning Roles

::: tip Who Can Assign
Super Administrators can assign members to any subject; **Managers** can assign members within the subjects they manage.
:::

1. Go to **Subjects** (this entry is visible only to Super Administrators and Managers).
2. On the target subject's row, click **Manage Members**.
3. Choose a teacher and a role (Viewer / Editor / Manager), then click **Add**. You can change an existing member's role or remove them at any time.

## Question Visibility: Public and Private

Each question has a visibility switch (set in the question edit dialog):

- **Public**: visible to all members of the subject (default). Use it for everyday practice questions.
- **Private**: visible only to its creator. Suitable for questions **being written / adapted**, not yet finalized, or intended for an exam that others shouldn't see in advance.

::: warning Private Questions Can't Be Added to Shared Compositions
A shared (team-visible) composition freezes question content into the composition. To prevent leaks, private questions **cannot** be added to shared compositions; your own personal compositions have no such restriction.
:::

## When No Subject Is Assigned

If a teacher hasn't been granted any subject yet, after signing in:

- The subject selector at the top shows **No subjects available · Contact an administrator for access.**;
- A banner at the top of the page tells them to contact an administrator;
- They are **not** prompted to create a subject (creating subjects is the administrator's job).

Once an administrator grants access under **Subjects → Manage Members**, a refresh is all it takes to start using the system.

## Rollout and Migration Notes

When you first upgrade to a version with permissions:

- **Existing administrator accounts stay unchanged** and remain Super Administrators;
- Other existing users are neither demoted nor assigned subjects automatically — administrators should grant access in member management as needed;
- **All existing questions are marked Public**, so their visibility doesn't change.

::: tip Fresh Install
On a fresh install, the setup wizard creates the first account as a Super Administrator, who then creates subjects, creates teacher accounts, and grants access.
:::
