
# ==============================================================================
# Stage 1: Base Setup
# Use Slim Linux for minimal base image size
# ==============================================================================
FROM python:3.13-slim AS python_base

# Python optimizations to avoid buffering issues and improve performance
ENV PYTHONUNBUFFERED=1
# Enable bytecode compilation for faster imports
ENV UV_COMPILE_BYTECODE=1
# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Set working directory for all subsequent commands
WORKDIR /app

# ==============================================================================
# Stage 2: Builder - Install dependencies in isolation
# ==============================================================================
FROM python_base AS builder
# Copy uv package manager from official image for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using cache mount to avoid re-downloading
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ==============================================================================
# Stage 3: Production - Final lightweight image
# ==============================================================================
FROM python_base AS prod

# Build argument to control which user runs the application
# Default to 'appuser' for production security
# Override with --build-arg RUN_AS_USER=root for local development on macOS
ARG RUN_AS_USER=appuser

# For Docker socket access from within the container (DEV only, not for PROD in production)
# Create docker group (with GID matching host docker group, typically 999 on macOS)
# This allows appuser to access the mounted docker socket
RUN groupadd -g 999 docker || true

# Create non-root user for security best practices and add to docker group
RUN groupadd -r appuser \
    && useradd -r -g appuser -G docker -d /app appuser

WORKDIR /app

# Create directories that the app needs to write to, with proper ownership
RUN mkdir -p models \
    && chown -R appuser:appuser models

# Copy pre-built virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy application source code and configuration files (respecting .dockerignore)
# Assign ownership to non-root user
COPY --chown=appuser:appuser . /app

# Make startup scripts executable (must be done before switching to non-root user)
RUN chmod +x /app/docker/*.sh

# SECURITY CONFIGURATION:
# =======================
# Production (default):  USER appuser (secure, non-root)
# Development (macOS):   USER root (for Docker socket access)
#
# Build for production:  docker build .
# Build for dev (macOS): docker build --build-arg RUN_AS_USER=root .
#
# Production alternative: Use Kubernetes/Consul/etcd instead of Docker socket

USER ${RUN_AS_USER}

# Add virtual environment to PATH for direct command access
ENV PATH="/app/.venv/bin:$PATH"

# ==============================================================================
# Entry point: Default command to run the application
# `CMD`: Used to start the main application at RUN time and NOT build time
# CMD can be overridden at runtime as needed BUT ENTRYPOINT cannot
# Here we default to starting the main app server
# ==============================================================================
CMD ["bash", "docker/run.sh"]
