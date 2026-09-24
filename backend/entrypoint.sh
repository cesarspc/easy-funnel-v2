#!/bin/bash
set -e

echo "Running database migrations..."
prisma migrate deploy --schema /app/prisma/schema.prisma

echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers --forwarded-allow-ips "*"
