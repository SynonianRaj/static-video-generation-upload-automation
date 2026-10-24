# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Install system dependencies including FFmpeg and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-liberation \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root application user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy dependency definition and install
COPY pyproject.toml /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Copy application source code and assets
COPY video_generator/ /app/video_generator/
COPY assets/ /app/assets/
COPY web/ /app/web/
COPY cli.py /app/
COPY server.py /app/
COPY README.md /app/

# Ensure output directory exists and is owned by appuser
RUN mkdir -p /app/outputs && chown -R appuser:appuser /app

USER appuser

# Environment defaults
ENV HOST=0.0.0.0 \
    PORT=8080 \
    WORKERS=1 \
    PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Launch uvicorn web server
CMD ["python", "server.py"]
