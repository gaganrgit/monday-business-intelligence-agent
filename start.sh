#!/usr/bin/env bash
# Launches FastAPI (backend) and Streamlit (frontend) together as a single service.
#
# FastAPI listens internally on BACKEND_INTERNAL_PORT (default 8000).
# Streamlit listens on PORT (the port external traffic routes to, default 8501)
# and communicates with FastAPI over localhost.

set -euo pipefail

export BACKEND_INTERNAL_PORT="${BACKEND_INTERNAL_PORT:-8000}"
export PORT="${PORT:-8501}"
export BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${BACKEND_INTERNAL_PORT}}"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo "Shutting down background processes..."
    if [ -n "${BACKEND_PID}" ] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
        kill -TERM "${BACKEND_PID}" 2>/dev/null || true
    fi
    if [ -n "${FRONTEND_PID}" ] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
        kill -TERM "${FRONTEND_PID}" 2>/dev/null || true
    fi
    wait "${BACKEND_PID}" "${FRONTEND_PID}" 2>/dev/null || true
    echo "Shutdown complete."
}

trap cleanup SIGINT SIGTERM EXIT

echo "Starting FastAPI backend on port ${BACKEND_INTERNAL_PORT}..."
python -m uvicorn backend.main:app --host 0.0.0.0 --port "${BACKEND_INTERNAL_PORT}" &
BACKEND_PID=$!

echo "Waiting for FastAPI backend health check on http://127.0.0.1:${BACKEND_INTERNAL_PORT}/health..."
MAX_RETRIES=30
RETRY_COUNT=0
HEALTHY=0

while [ "${RETRY_COUNT}" -lt "${MAX_RETRIES}" ]; do
    if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${BACKEND_INTERNAL_PORT}/health')" 2>/dev/null; then
        HEALTHY=1
        echo "FastAPI backend is healthy and ready."
        break
    fi
    if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
        echo "Error: FastAPI backend process exited unexpectedly."
        exit 1
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    sleep 1
done

if [ "${HEALTHY}" -ne 1 ]; then
    echo "Error: FastAPI backend failed to become healthy within ${MAX_RETRIES} seconds."
    exit 1
fi

echo "Starting Streamlit frontend on port ${PORT}..."
streamlit run frontend/streamlit_app.py \
    --server.port "${PORT}" \
    --server.address 0.0.0.0 \
    --server.headless true &
FRONTEND_PID=$!

wait -n "${BACKEND_PID}" "${FRONTEND_PID}"
