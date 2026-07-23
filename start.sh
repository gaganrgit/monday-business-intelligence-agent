#!/usr/bin/env bash
# Launches FastAPI (backend) and Streamlit (frontend) together as a
# single Render service.
#
# FastAPI listens internally on port 8000.
# Streamlit listens on $PORT (the port Render routes external traffic to)
# and talks to FastAPI over localhost, avoiding any CORS issues since
# everything runs inside the same container.

set -e

export BACKEND_INTERNAL_PORT="${BACKEND_INTERNAL_PORT:-8000}"
export BACKEND_URL="${BACKEND_URL:-http://localhost:${BACKEND_INTERNAL_PORT}}"
export PORT="${PORT:-8501}"

echo "Starting FastAPI backend on port ${BACKEND_INTERNAL_PORT}..."
PORT="${BACKEND_INTERNAL_PORT}" python -m uvicorn backend.main:app --host 0.0.0.0 --port "${BACKEND_INTERNAL_PORT}" &
BACKEND_PID=$!

# Give the backend a moment to boot before Streamlit starts probing it.
sleep 3

echo "Starting Streamlit frontend on port ${PORT}..."
streamlit run frontend/streamlit_app.py \
  --server.port "${PORT}" \
  --server.address 0.0.0.0 \
  --server.headless true &
FRONTEND_PID=$!

# If either process dies, bring the whole container down so Render restarts it.
wait -n "${BACKEND_PID}" "${FRONTEND_PID}"
