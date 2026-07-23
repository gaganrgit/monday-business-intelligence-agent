FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8501 \
    BACKEND_INTERNAL_PORT=8000

WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications first to leverage Docker layer caching
COPY requirements.txt ./
COPY backend/requirements.txt ./backend/
COPY frontend/requirements.txt ./frontend/

RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and startup script
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY start.sh ./

RUN chmod +x start.sh

# Security: Create non-root user and transfer file ownership
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT}/ || exit 1

CMD ["bash", "start.sh"]
