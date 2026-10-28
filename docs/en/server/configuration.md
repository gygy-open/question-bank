# Configuration Reference

The server edition is configured through the `.env` file (read by `docker-compose.yml`). Copy `.env.example` to `.env` and edit as needed.

::: warning Sensitive Information
`.env` contains keys and passwords and is excluded by `.gitignore`. **Never commit it to the repository.**
:::

## Required

| Variable | Description | Example / How to generate |
|------|------|----------------|
| `SECRET_KEY` | JWT signing key; must be a long random value | `openssl rand -hex 32` |
| `MYSQL_ROOT_PASSWORD` | MySQL root password | A strong password of your choice |
| `MYSQL_PASSWORD` | Password for the application database user | A strong password of your choice |

## Database

| Variable | Default | Description |
|------|--------|------|
| `MYSQL_DATABASE` | `question_bank` | Database name |
| `MYSQL_USER` | `question_bank` | Application database user |
| `DB_URL` | `mysql+aiomysql://question_bank:<MYSQL_PASSWORD>@mysql:3306/question_bank` | Backend connection string; usually no need to set manually |

## Vector Database (ChromaDB)

| Variable | Default | Description |
|------|--------|------|
| `CHROMADB_HOST` | `chromadb` | ChromaDB host (container name) |
| `CHROMADB_PORT` | `8000` | In-container port |

## Runtime

| Variable | Default | Description |
|------|--------|------|
| `IMAGE_TAG` | `latest` | Tag of the prebuilt images to pull; set to a specific version (e.g. `1.2.0`) to pin it |
| `LOG_LEVEL` | `INFO` | Log level (`DEBUG`/`INFO`/`WARNING`/`ERROR`) |
| `DATA_DIR` | `/data` | Writable backend data directory (uploads, static media, runtime config); preset in the image, usually no need to change |
| `MCP_ALLOWED_ORIGINS` | empty | Comma-separated origins allowed to call the [MCP server](/en/features/mcp) cross-site from a browser (e.g. `https://inspector.example.com`). Native MCP clients need no configuration |

Switching a server in mainland China to the Alibaba Cloud mirrors requires no extra variables — just one more file to download; see [Mainland China Mirrors](/en/server/docker#china-mirrors).

## AI Configuration Is Not in .env

AI providers, models, API keys and other **dynamic business settings are stored in the database** and managed through the UI rather than environment variables. After logging in, configure them in [AI Providers & Models](/en/admin/ai-config); changes take effect without a restart.

Likewise, business parameters such as review thresholds and prompt templates are managed in the UI; see [System Settings](/en/admin/system-settings).

::: tip Static vs. Dynamic Configuration
- **Static configuration** (fixed before startup): `.env` / environment variables, such as keys and the database connection.
- **Dynamic configuration** (changeable at runtime): tables such as `system_setting` in the database, hot-updated through the UI.
:::

## After Changing Configuration

After editing `.env`, recreate the containers for the changes to take effect:

```bash
docker compose up -d
```
