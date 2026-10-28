# Docker Compose Deployment

The server edition launches the full stack with a single Docker Compose command, making it suitable for teams and production. The stack includes:

| Service | Purpose | Port (default) |
|------|------|-----------|
| `mysql` | Primary database (MySQL 8.0) | 3306 |
| `chromadb` | Vector database (knowledge point RAG) | 8001 → container 8000 |
| `backend` | FastAPI backend API | 8000 |
| `worker` | Background jobs (imports, etc.) | — |
| `frontend` | Frontend (SPA served by Nginx) | 80 |

## Prerequisites

- A server with **Docker** and **Docker Compose** installed (Linux recommended)
- Access to an AI provider (Gemini / OpenAI / compatible API)

Images are built by CI and published to GitHub Container Registry (`ghcr.io/gygy-open/question-bank-backend`, `ghcr.io/gygy-open/question-bank-frontend`). Pulling them directly is recommended; there is no need to build on the server. In `docker-compose.yml`, `backend` / `worker` / `frontend` already have the corresponding `image:` configured and pull `latest` by default.

## Deployment Steps

```bash
# 1. Only docker-compose.yml and .env.example are needed; no need to clone the full repository
curl -O https://raw.githubusercontent.com/gygy-open/question-bank/main/docker-compose.yml
curl -O https://raw.githubusercontent.com/gygy-open/question-bank/main/.env.example
cp .env.example .env
```

Edit `.env` and set **at least** the following (see [Configuration Reference](/en/server/configuration) for the full list):

- `SECRET_KEY` — JWT signing key; use a random value: `openssl rand -hex 32`
- `MYSQL_ROOT_PASSWORD` — MySQL root password
- `MYSQL_PASSWORD` — password for the application database user

```bash
# 2. Pull the images and start all services
docker compose pull
docker compose up -d
```

3. Open QuestionBank in a browser. The first visit opens the setup wizard, where you create the first superuser directly (the database is already configured via `DB_URL`, so there is nothing to choose).

   Alternatively, use the command line (creates `admin` / `password`; change the password immediately after logging in):

   ```bash
   docker compose exec backend python scripts/create_superuser.py
   ```

::: warning
Whoever opens the page first can create the superuser. Complete the setup as soon as deployment finishes.
:::

::: tip Building locally / customizing?
After cloning the full repository, leave `IMAGE_TAG` in `.env` empty or ignore it, and run `docker compose up -d --build` to build images from local source (`docker-compose.yml` declares both `image` and `build`; `--build` builds locally and overwrites the tag of the same name). This suits contributors or anyone who needs a custom Dockerfile.
:::

## Mainland China Mirrors {#china-mirrors}

When publishing to GHCR, CI also pushes **the same images** to Alibaba Cloud Container Registry (ACR, Hangzhou), with tags identical to the international ones; mysql / chromadb are mirrored as well. All repositories are public, so no `docker login` is required.

It takes just one extra command on top of the deployment steps — download the mirror config as `docker-compose.override.yml`, which Compose loads automatically:

```bash
curl -o docker-compose.override.yml \
  https://raw.githubusercontent.com/gygy-open/question-bank/main/docker-compose.cn.yml

docker compose pull
docker compose up -d
```

No extra environment variables or `-f` flags are needed, and all subsequent `docker compose ...` commands are exactly as documented. To go back to pulling from GHCR, just delete `docker-compose.override.yml`.

::: tip Want to keep the original file name?
You can also download it as `docker-compose.cn.yml`, but then every command must explicitly include both files:

```bash
docker compose -f docker-compose.yml -f docker-compose.cn.yml up -d
```
:::

## Access

- Frontend: `http://<server-IP>` (port 80 by default)
- Backend API docs (Swagger): `http://<server-IP>:8000/docs`
- MCP server: `http://<server-IP>/api/mcp`, proxied to the backend by the frontend nginx; see [MCP Access](/en/features/mcp)

## Initial Setup

After logging in as the superuser:

1. The first login automatically opens the onboarding page, where you create the first subject (the question bank is organized by subject).
2. Add a provider / model in [AI Providers & Models](/en/admin/ai-config) and activate it.
3. Create accounts for team members in [Users](/en/admin/users).
4. Start with [Smart Import](/en/features/import) or enter questions manually.

## Common Operations Commands

```bash
# Check service status
docker compose ps

# View logs
docker compose logs -f backend
docker compose logs -f worker

# Stop / start
docker compose down
docker compose up -d

# Update to a new version (pull the latest images)
docker compose pull
docker compose up -d
```

The `latest` tag is used by default (the latest build of the `main` branch). To pin a specific version, set `IMAGE_TAG` in `.env` (e.g. `1.2.0`), then run `docker compose pull && docker compose up -d`. Available tags are listed on the [container package page](https://github.com/gygy-open/question-bank/pkgs/container/question-bank-backend).

### Trying a Pre-release (Alongside the Stable Version)

A pre-release upgrades data to a new format that cannot be rolled back, so do not simply change `IMAGE_TAG` of your production deployment to a pre-release. Instead, set up a separate deployment and copy the data over:

1. Create a new directory (e.g. `question-bank-alpha`) and copy `docker-compose.yml`, `.env` (and `docker-compose.override.yml`, if any).
2. In the new directory's `.env`, set:
   ```bash
   COMPOSE_PROJECT_NAME=question-bank-alpha   # separate containers and volumes
   IMAGE_TAG=1.5.0-alpha.1                    # pre-release tag
   HTTP_PORT=8080                             # run alongside the stable version
   ```
3. Copy the stable version's data into the new volumes (stop the stable version during the copy to keep MySQL data consistent):
   ```bash
   (cd stable-deployment-dir && docker compose stop)
   for v in mysql_data app_data chromadb_data; do
     docker run --rm -v question-bank_$v:/from -v question-bank-alpha_$v:/to alpine cp -a /from/. /to/
   done
   (cd stable-deployment-dir && docker compose start)
   ```
4. Run `docker compose up -d` in the new directory and visit `http://server:8080`. The pre-release only upgrades this copy.

When no longer needed, run `docker compose down -v` in the new directory to remove the pre-release and its volumes; the stable version is unaffected.

See also [Operations](/en/server/operations) and [Database & Migrations](/en/server/database).

## Data Persistence

- **MySQL data**: named volume `mysql_data`.
- **Vector data**: named volume `chromadb_data`.
- **Uploaded files / static assets**: named volume `app_data`, mounted at `/data` in the backend container (corresponds to `DATA_DIR`), containing `uploads/` and `static/media/`.

The backend container starts its entrypoint as root, changes the owner of `/data` to the in-container `nonroot` user (uid 999), and then drops privileges, so neither named volumes nor host bind mounts cause permission issues.

Backups must cover all of the data above; see [Database & Migrations](/en/server/database).

### Upgrading from Older Versions (Volume Merge)

Older versions used two volumes, `uploads_data:/app/uploads` and `static_data:/app/static`. After upgrading they are replaced by a single `app_data:/data`, so the data must be moved once (`question-bank_` is the Compose project name prefix):

```bash
docker compose down
docker volume create question-bank_app_data
docker run --rm \
  -v question-bank_static_data:/old/static \
  -v question-bank_uploads_data:/old/uploads \
  -v question-bank_app_data:/data \
  alpine sh -c 'mkdir -p /data/static /data/uploads \
    && cp -a /old/static/. /data/static/ \
    && cp -a /old/uploads/. /data/uploads/'
docker compose pull
docker compose up -d
```

After confirming that images and uploaded files work correctly, remove the old volumes:

```bash
docker volume rm question-bank_static_data question-bank_uploads_data
```
