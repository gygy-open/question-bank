# Operations

Common day-to-day operations and troubleshooting for the server edition (Docker Compose).

## Service Management

```bash
# Check the status of each service
docker compose ps

# Start / stop / restart
docker compose up -d
docker compose down
docker compose restart backend

# Rebuild (after changing code / configuration)
docker compose up -d --build
```

## Logs

```bash
# Follow in real time
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend

# Last 200 lines
docker compose logs --tail=200 backend
```

The log level is controlled by `LOG_LEVEL` in `.env` (default `INFO`). For troubleshooting, temporarily set it to `DEBUG` and recreate the containers.

## Background Jobs (Worker) {#background-worker}

The `worker` service handles asynchronous jobs (such as imports). If an import is stuck at **Processing**, check the worker logs first:

```bash
docker compose logs -f worker
```

Make sure the worker and backend use the same `DB_URL` and `CHROMADB_HOST` (already aligned in `docker-compose.yml` by default).

## Upgrading

```bash
git pull
docker compose up -d --build
# Migrations are applied automatically by the migrate service; to re-run them separately
docker compose run --rm migrate
```

It is recommended to [back up](/en/server/database#backup-and-restore-mysql) before upgrading.

### Post-Upgrade Data Cleanup

After schema migrations complete, the worker runs a one-time data cleanup in the background (for example, moving images uploaded into questions by older versions into the media library). Once done, it is recorded in the `system_settings` table under keys starting with `data_migration.` (internal records, not shown on the settings page and not modifiable via the API), and it does not run again. Progress and reports can be viewed in the worker logs:

```bash
docker compose logs worker | grep -i "data migration"
```

Failures are only logged and do not affect normal use; the worker retries on its next start. If multiple workers start at the same time, only one runs it. You can also run the legacy media migration manually (dry run by default):

```bash
docker compose exec backend python scripts/migrate_media_assets.py
docker compose exec backend python scripts/migrate_media_assets.py --apply
```

## Troubleshooting

| Symptom | What to check |
|------|---------|
| Frontend won't load | Run `docker compose ps` to see whether `frontend`/`backend` are Up; check the backend logs |
| Login error / token invalid | Check whether `SECRET_KEY` was changed (changing it invalidates issued tokens) |
| AI features fail | Check the [AI Providers & Models](/en/admin/ai-config) configuration, API key, and network connectivity |
| Knowledge point search returns nothing | Confirm the `chromadb` service is healthy and an embedding model is configured |
| Import never finishes | Check the `worker` logs; confirm the AI model is available |
| Database connection fails | Confirm the `mysql` health check passes and the password matches `DB_URL` |


## Reverse Proxy and HTTPS (Optional)

To serve via a domain / HTTPS, put an Nginx / Caddy / Traefik reverse proxy in front and forward 80/443 to `frontend`. Make sure to:

- expose only the necessary ports;
- configure HTTPS certificates;
- keep the backend `SECRET_KEY` safe.

::: warning Security
Before exposing the service to the public internet, always use strong passwords and HTTPS, and restrict allowed sources. For lightweight intranet collaboration, consider the desktop edition's [LAN Sharing](/en/desktop/lan-sharing) first.
:::
