#!/bin/sh
# Local demo stack: the whole funnel running on this machine, no login.
#
#   sh demo.sh up      build + start, apply migrations, seed browsable data
#   sh demo.sh seed     re-seed only (idempotent: it truncates what it seeded)
#   sh demo.sh web      start the Vite dev server that auto-signs-in
#   sh demo.sh down     stop the stack, keep its data
#   sh demo.sh reset    stop and delete the demo's data volumes
#   sh demo.sh logs     follow backend logs
#
# The project name matters. `docker compose` would otherwise reuse the
# `easy-funnel` project from docker-compose.yml, whose volumes may already hold
# a database created with a different password — Postgres only reads
# POSTGRES_PASSWORD when it initialises an empty data directory, so an existing
# volume keeps its old credentials and the backend cannot authenticate. Running
# under a separate project keeps the demo's data beside yours, never on top of
# it, so `reset` can never destroy the main stack's database.
set -eu

PROJECT=easy-funnel-demo
COMPOSE="docker compose -p $PROJECT -f docker-compose.yml -f docker-compose.demo.yml"
WEB_PORT="${WEB_PORT:-5174}"

case "${1:-up}" in
  up)
    [ -f .env ] || { echo "Missing .env — copy docker.env.example and fill it in."; exit 1; }
    $COMPOSE up --build -d
    echo "Waiting for the API to report healthy..."
    # The backend applies migrations on boot, so it is only ready once /health answers.
    until curl -fsS http://localhost:8000/health >/dev/null 2>&1; do sleep 2; done
    sh "$0" seed
    echo
    echo "Storefront + API : http://localhost:8088"
    echo "Admin (no login) : run 'sh demo.sh web', then http://localhost:$WEB_PORT/admin"
    ;;
  seed)
    # Goes through the real admin + public APIs, so seeded rows pass the same
    # validation, fraud evaluation and audit rules a merchant would hit.
    $COMPOSE exec -T backend python -m scripts.seed_dev_data --username admin
    ;;
  web)
    # The dev server is what makes the demo login-free: VITE_DEMO_AUTOLOGIN is
    # read only in `vite dev`, never in a production build or the test runner.
    [ -f frontend/.env.local ] || { echo "Missing frontend/.env.local (demo credentials)."; exit 1; }
    # Node is installed Windows-side (nvm4w). WSL inherits the Windows `pnpm`
    # shim through PATH interop but cannot execute the Windows node binary off
    # the /mnt/c mount, so the shim's own `exec node` fails with the unhelpful
    # "exec: node: Permission denied". Say what is actually wrong instead.
    if ! command -v node >/dev/null 2>&1; then
      echo "node is not on PATH in this shell."
      case "$(uname -r 2>/dev/null)" in
        *microsoft*|*Microsoft*|*WSL*)
          echo
          echo "This is WSL, and Node/pnpm are installed on the Windows side."
          echo "Run this target from Git Bash or PowerShell instead:"
          echo "    sh demo.sh web"
          echo
          echo "The docker targets (up, seed, down, reset, logs) work from either"
          echo "shell, because Docker Desktop exposes the engine to WSL."
          ;;
      esac
      exit 1
    fi
    cd frontend && pnpm exec vite --port "$WEB_PORT" --strictPort
    ;;
  down)  $COMPOSE down ;;
  reset) $COMPOSE down --volumes ;;
  logs)  $COMPOSE logs -f backend ;;
  *) echo "usage: sh demo.sh [up|seed|web|down|reset|logs]"; exit 1 ;;
esac
