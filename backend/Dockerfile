# COD Commerce Platform Backend
# Single FastAPI container. Works on Railway, Koyeb, or any Docker host.
#
# Build context MUST be the repository root. Railway does this by default when
# the Dockerfile path is set to /backend/Dockerfile:
#   docker build -t cod-commerce-backend:v1.0.0 -f backend/Dockerfile .
#
# Deliberately single-stage for the Python layer: prisma-client-py resolves its
# generated client *and* its engine binaries through a cache directory, so
# splitting build/runtime stages silently drops the engines and fails at the
# first query. Every dependency ships a manylinux wheel for cp312, so no
# compilers are needed and a single stage stays reasonably small.

# Node is required at runtime, not just at build time: `prisma migrate deploy`
# shells out to the Prisma CLI, which is a Node program. Without a Node on the
# image, prisma-client-py downloads one via nodeenv on *every* container start,
# making boot depend on the network. Pinned Node image, matched to the Debian
# trixie base below so glibc is compatible.
FROM node:22-trixie-slim AS node

FROM python:3.12-slim

WORKDIR /app

# Runtime system libraries.
#   curl              -> container healthcheck
#   libjpeg/webp/zlib -> Pillow banner variant generation
#   libatomic1        -> prisma query engine
#   openssl           -> prisma engine TLS to Neon/Postgres
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libjpeg62-turbo \
    libwebp7 \
    zlib1g \
    libatomic1 \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Bake in Node + npm and tell prisma-client-py to use them instead of
# downloading its own copy at runtime.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && node --version && npm --version

# Prisma CLI and engine binaries are cached under /app instead of $HOME, so the
# same paths stay readable after switching to the non-root user below (build
# runs as root with HOME=/root; runtime does not).
ENV PRISMA_USE_GLOBAL_NODE=true \
    PRISMA_BINARY_CACHE_DIR=/app/.prisma-engines \
    PRISMA_HOME_DIR=/app/.prisma-home \
    NPM_CONFIG_CACHE=/app/.npm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    GEOIP_DATABASE_PATH=/app/geoip/GeoLite2-Country.mmdb

# Dependencies first so application edits do not invalidate this layer.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Schema + migrations. `prisma generate` builds the Python client and fetches
# the query engine; `prisma py fetch` also pulls the schema (migration) engine
# so `migrate deploy` at startup needs no downloads.
COPY prisma/ prisma/
RUN prisma generate --schema prisma/schema.prisma \
    && prisma py fetch

# Application source.
COPY backend/app/ app/
COPY backend/scripts/ scripts/

# GeoIP database directory. Leaving it empty is safe: GeoIpResolver reports
# "unavailable" and fraud checks skip geo rules rather than rejecting orders.
RUN mkdir -p /app/geoip

# Non-root runtime user, owning the engine/CLI caches it must read and execute.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Documents the local default. Railway injects its own $PORT and Koyeb uses 8080.
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8080}/health" || exit 1

# Apply pending migrations, then serve.
#   --proxy-headers / --forwarded-allow-ips: Railway and Koyeb both terminate
#   TLS at a proxy. Without these, request.client.host is the proxy address and
#   every fraud, GeoIP, and rate-limit decision keys off the wrong IP.
CMD ["sh", "-c", "prisma migrate deploy --schema /app/prisma/schema.prisma && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips '*'"]
