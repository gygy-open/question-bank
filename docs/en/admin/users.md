# Users

This page covers creating, importing, and maintaining **accounts**. For the role and permission model (Super Administrator, subject roles, question visibility, etc.), see [Permissions & Roles](/en/admin/permissions).

## User Fields

- Username, full name, avatar
- `is_superuser` (Super Administrator flag), `is_active` (enabled status)
- `last_login`, `login_count` (sign-in statistics)

> Subject membership and roles are not set on the user account itself. They are granted per subject under **Subjects → Manage Members**; see [Permissions & Roles](/en/admin/permissions).

## Common Tasks

- **Create a user**: a Super Administrator creates the account in Users and sets its role.
- **Batch import**: a Super Administrator can create many accounts at once from Excel; see below.
- **Edit profile**: users can edit their own profile.
- **Change password**: users can change their own password.
- **Enable / disable**: administrators can disable accounts.

## Batch Importing Users

On the **Users** page, a Super Administrator can click **Batch Import** to create many accounts at once from Excel:

1. Download the `.xlsx` template.
2. Fill in the template columns:

   | Column | Required | Description |
   |----|:---:|------|
   | Username | ✅ | Must be unique, and must not duplicate other rows in the file or existing users |
   | Full Name | ✅ | User's full name |
   | Password | ✅ | At least 6 characters |
   | Admin | ❌ | Enter **Yes** to create an administrator; leave blank for a regular user |

3. Upload the file (`.xlsx` only, up to 5 MB).
4. The system validates and saves each row, then returns the **number of successes** and **per-row failure details**. You can copy the errors with one click, fix them, and import again.

::: tip
Valid rows are created immediately; an invalid row doesn't affect the others. If you upload again, existing usernames are skipped and noted in the details.
:::

## Self Sign-Up

Off by default. A Super Administrator can enable it under **Sign-Up** in [System Settings](/en/admin/system-settings):

- **Allow Self Sign-Up**: when on, the sign-in page shows a **Sign up** link and visitors can create their own accounts (regular users only; nobody can make themselves an administrator).
- **Require Administrator Approval**: when on, newly registered accounts are disabled by default (`is_active=false`) and can sign in only after an administrator enables them in Users.

## First-Time Setup

Setup has two independent stages, and the wizard automatically starts at the right step based on the current state:

1. **Database**: shown only when no database is configured (no `DB_URL` environment variable and no `config.json`). Choose the database type (SQLite / MySQL) and verify the connection; migrations then run and the configuration is saved.
2. **First Super Administrator**: shown whenever the database is ready but there is no **enabled** Super Administrator yet, regardless of how the database was configured.

Therefore:

- **Desktop edition**: open the wizard via **Open QuestionBank** in the tray and complete both steps.
- **Docker / server edition**: the database is already provided by `DB_URL`, so the first visit to the web page goes straight to the **Administrator** step.

Until setup is complete, every API except the wizard returns `503`, and pages such as sign-in and sign-up are unavailable.

You can also create a Super Administrator with a command-line script (it creates `admin` / `password`; change the password immediately after signing in):

```bash
docker compose exec backend python scripts/create_superuser.py
```

::: warning Keep at Least One Super Administrator
The system won't let you delete, demote, or disable **the last enabled Super Administrator**. If you bypass the UI and edit the database directly so that no enabled Super Administrator remains, the next visit will return to the **Administrator** setup step.
:::
