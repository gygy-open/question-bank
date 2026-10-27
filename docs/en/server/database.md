# Database & Migrations

QuestionBank supports two databases, kept compatible through a shared data model and Alembic migrations:

- **SQLite**: default for the desktop edition; zero configuration, single file.
- **MySQL 8.0**: default for the server edition; for teams and production.

## Migrations (Alembic)

Schema changes are managed with [Alembic](https://alembic.sqlalchemy.org/). Migration scripts live in `backend/alembic/versions/`.

In the server edition, a dedicated `migrate` service applies migrations automatically on every `docker compose up`, and `backend` / `worker` start only after it exits successfully. To run manually:

```bash
# Upgrade to the latest version
docker compose run --rm migrate

# Show the current version
docker compose run --rm migrate alembic current
```

In a development environment (outside containers):

```bash
cd backend
uv run alembic upgrade head
```

Adding a migration (after changing models):

```bash
uv run alembic revision --autogenerate -m "describe this change"
uv run alembic upgrade head
```

::: tip Dual-Database Baseline
The repository currently uses a "dual-database baseline" migration (shared by SQLite / MySQL). Legacy MySQL-only migrations are archived in `backend/alembic/versions_archive_mysql/` and can generally be ignored.
:::

## Backup and Restore (Server / MySQL) {#backup-and-restore-mysql}

**Backup:**

```bash
# Export MySQL data
docker compose exec mysql mysqldump -u root -p question_bank > backup.sql

# Also back up the vector store and uploaded files
tar czf data-backup.tgz chromadb_data backend/uploads backend/static
```

**Restore:**

```bash
# Restore MySQL
docker compose exec -T mysql mysql -u root -p question_bank < backup.sql

# Restore data files (extract and overwrite)
tar xzf data-backup.tgz
```

## Backup (Desktop / SQLite)

Close the desktop app, then copy the data directory:

```
%APPDATA%\QuestionBank
```

See [Personal Use · Backup and Restore](/en/desktop/personal#backup-and-restore) for details.

## Migrating from Desktop to Server

The desktop and server editions share the same models but use different databases (SQLite → MySQL). Approaches:

1. **Small data set / same structure**: re-import the original files in the server edition with [Smart Import](/en/features/import), or re-enter them manually.
2. **Full migration required**: export the SQLite data, convert it, and write it into MySQL (Alembic guarantees the schemas match).

::: warning Back Up Before Migrating
Before any migration, back up both the desktop data directory and the server database.
:::
