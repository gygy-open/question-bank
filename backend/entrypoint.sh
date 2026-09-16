#!/bin/sh

# Container startup entry script
# Normalise ownership of the data volume, then drop privileges.
# Database migrations are owned by the dedicated `migrate` service.

set -e  # Exit immediately on error

: "${DATA_DIR:=/data}"

# A named volume or bind mount does not inherit the image's ownership (Docker
# only seeds that once, into a brand-new empty volume), so on an existing or
# host-provided mount $DATA_DIR can be root-owned. Fix it as root, then drop to
# nonroot. `find ! -user` avoids re-walking every media file on each start.
if [ "$(id -u)" = "0" ]; then
    echo "Preparing data directory $DATA_DIR..."
    mkdir -p "$DATA_DIR/static/media" "$DATA_DIR/uploads"
    find "$DATA_DIR" ! -user nonroot -exec chown nonroot:nonroot {} +
    exec gosu nonroot "$0" "$@"
fi

echo "Starting the application..."

exec "$@"
