#!/bin/sh
set -eu

compose_file="docker-compose.fresh-test.yml"

cleanup() {
  docker compose -f "$compose_file" down --volumes --remove-orphans
}

trap cleanup EXIT INT TERM
cleanup
docker compose -f "$compose_file" --profile test-build build frontend-test
docker compose -f "$compose_file" up --build --abort-on-container-exit --exit-code-from backend-test backend-test
