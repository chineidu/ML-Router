#!/bin/bash
set -e

echo "🚀 Running database migrations..."
/app/.venv/bin/alembic upgrade head
echo "✅ Database migrations completed."

# Give some time for the database to settle
sleep 2

# Default values for environment variables
WORKERS="${WORKERS:-2}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
# How long (seconds) to wait for a worker to finish handling a request before killing it
TIMEOUT="${TIMEOUT:-60}"

echo "🚀 Starting FastAPI on $HOST:$PORT with $WORKERS workers and timeout $TIMEOUT seconds..."

# -----------------------------
# Launch Gunicorn (ASGI server for production)
# -----------------------------
# Key notes:
# - `exec` replaces this shell process with Gunicorn → ensures it receives SIGTERM/SIGINT directly.
# - `src.api.app:app` is the import path to the FastAPI app object.
# - `--worker-tmp-dir /dev/shm` → use RAM for heartbeat files, improves performance in containers.
# - `-k uvicorn.workers.UvicornWorker` → use Uvicorn worker for async FastAPI apps.
# - `--preload` → load app in master process, saves memory.
# - `--timeout` → maximum time a worker can take to handle a request before being killed.
# - `-w` → number of worker processes.
# - `--bind` → interface and port to listen on.
exec /app/.venv/bin/gunicorn \
    src.api.app:app \
    --worker-tmp-dir /dev/shm \
    --pythonpath . \
    -k uvicorn.workers.UvicornWorker \
    -w "$WORKERS" \
    --preload \
    --timeout "$TIMEOUT" \
    --bind "$HOST:$PORT"
