# ============================================================
# AI Portfolio Backend - Production Dockerfile
# ============================================================
# This Dockerfile is optimized for production deployment.
# For development, run locally with uvicorn.
# ============================================================

FROM python:3.12-slim

WORKDIR /app

# Set environment to production by default
# Override with --build-arg ENVIRONMENT=development for dev builds
ARG ENVIRONMENT=production
ENV ENVIRONMENT=${ENVIRONMENT}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data/chroma /app/data/cache

# Expose port
EXPOSE 8000

# Run application
# Host 0.0.0.0 is required for container networking
# Port 8000 is internal container port (mapped externally via docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]