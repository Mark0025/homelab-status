FROM python:3.12-slim

# Install system dependencies (git needed for subprocess git calls in mdops.py and git_history.py)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy package files first for layer caching
COPY pyproject.toml uv.lock ./
COPY homelab_status/ ./homelab_status/

# Install dependencies and the package via uv
RUN uv pip install --system --no-cache .

# Data directory for mounted volumes
RUN mkdir -p /data

EXPOSE 8800

CMD ["uvicorn", "homelab_status.web:api", "--host", "0.0.0.0", "--port", "8800"]
