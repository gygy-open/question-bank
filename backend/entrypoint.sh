#!/bin/sh

# Container startup entry script
# Execute database migrations, initialize system configuration

set -e  # Exit immediately on error
echo "Starting backend entrypoint script..."

echo "Applying database migrations..."

alembic upgrade head

echo "Database migrations applied."

echo "Backend entrypoint script completed."

echo "Starting the application..."

exec "$@"
