# syntax=docker/dockerfile:1.7

# Multi-stage build. Stage 1 compiles the wheel and installs deps into a
# throwaway virtualenv using uv; stage 2 is a distroless-python image that
# copies in the compiled deps + the application. The result is a ~80 MB
# multi-arch image (amd64 + arm64) with zero build tools on the runtime
# layer.

# ---------- builder ----------
FROM python:3.12-slim-bookworm AS builder

# Install uv (fast, reproducible resolves).
COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy only what uv needs to resolve, to maximise layer caching.
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY src ./src

# Install the project (no dev deps, with [sdk] extra for download tool).
RUN uv sync --no-dev --extra sdk --locked

# Strip __pycache__ to shave a few MB off the final image.
RUN find /app/.venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ---------- runtime ----------
# Distroless-python keeps the runtime image minimal — no shell, no package
# manager, no CVE surface from unused binaries. Operators who need a shell
# for debugging can override CMD to run an exec shell from uv/python.
FROM gcr.io/distroless/python3-debian12:nonroot AS runtime

LABEL org.opencontainers.image.title="mcp-server-roboflow" \
      org.opencontainers.image.description="Hardened MCP server for the Roboflow API." \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/MayankD409/Roboflow-MCP-Server"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv

COPY --from=builder --chown=nonroot:nonroot /app /app

WORKDIR /app
USER nonroot

# The default entrypoint runs the MCP server on stdio. Operators wire this
# into their MCP client exactly like `uvx mcp-server-roboflow` on a normal
# host — just with `docker run` as the command.
ENTRYPOINT ["/app/.venv/bin/mcp-server-roboflow"]
