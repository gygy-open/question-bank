FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Disable Python downloads, because we want to use the system interpreter
# across both images. If using a managed Python version, it needs to be
# copied from the build image into the final image; see `standalone.Dockerfile`
# for an example.
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# Copy the project and sync
COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


# Runtime stage
FROM python:3.13-slim-trixie AS pro

RUN apt-get update && apt-get install -y dos2unix && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

# Fix for aiomysql/getpass issue when running with arbitrary UID
ENV USER=nonroot

# Copy only the virtual environment from builder
COPY --from=builder --chown=nonroot:nonroot /app/.venv /app/.venv

COPY --chown=nonroot:nonroot . /app/

RUN dos2unix /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"

USER nonroot

WORKDIR /app

ENTRYPOINT  ["/app/entrypoint.sh"]

CMD [ "fastapi", "run", "app/main.py" ]