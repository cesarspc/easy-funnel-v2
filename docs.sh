#!/bin/sh
# Publish the backend API reference as a static site.
#
#   sh docs.sh build     regenerate api-docs/openapi.json from the route table
#   sh docs.sh diagram   regenerate api-docs/architecture.html from its spec
#   sh docs.sh serve     preview at http://localhost:8099
#   sh docs.sh check     CI: fail if the committed document is out of date
#   sh docs.sh vercel    deploy to Vercel
#   sh docs.sh pages     deploy to Cloudflare Pages
#   sh docs.sh r2        upload to a Cloudflare R2 bucket (see the note below)
#
# The published site is static files only — an API reference at /, a system
# architecture diagram at /architecture, the OpenAPI document, and a headers
# file. Nothing calls the API, so the backend does not need to be running,
# reachable, or deployed at all for any of it to work.
#
# `build` does not need a running stack either: the document is derived from the
# imported application object, not from a live server.
set -eu

DOCS_DIR=api-docs
PORT="${DOCS_PORT:-8099}"
PROJECT="${PAGES_PROJECT:-easy-funnel-api-docs}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-easy-funnel-demo}"

# BOTH published pages describe the PRODUCTION repository, not this one. This
# checkout carries demo scaffolding — a self-hosted compose stack, a login-free
# dev server, a store-settings screen — that the deployed system does not have,
# so generating either page from here would publish the demo rig instead of the
# product. The diagram additionally pins a revision and verifies every cited
# source path against it, and that revision belongs to the production repo.
SOURCE_REPO="${SOURCE_REPO:-$PWD/../../GitHub/easy-funnel}"

# Writes the document to $1, from the production repository. Never contacts a
# database: the schema comes from the imported application object, so this works
# whether or not anything is running.
build_to() {
  out="$1"
  if [ ! -d "$SOURCE_REPO/backend" ]; then
    echo "Production repository not found at $SOURCE_REPO"
    echo "Set SOURCE_REPO to its checkout."
    exit 1
  fi

  # Preferred: that repository's own virtual environment, which already has its
  # dependencies and a generated Prisma client.
  for py in "$SOURCE_REPO/backend/.venv/Scripts/python.exe" "$SOURCE_REPO/backend/.venv/bin/python"; do
    if [ -x "$py" ]; then
      (cd "$SOURCE_REPO/backend" && "$py" -m scripts.export_openapi --stdout) > "$out"
      return
    fi
  done

  # Fallback: build its backend image and export from there. Needs no local
  # Python at all, and still opens no connection.
  echo "No virtualenv in the production repo; exporting through its backend image."
  ( cd "$SOURCE_REPO" && docker build -q -f backend/Dockerfile -t easy-funnel-docs-export . >/dev/null )
  docker run --rm --entrypoint python easy-funnel-docs-export -m scripts.export_openapi --stdout > "$out"
}

build() {
  build_to "$DOCS_DIR/openapi.json"
  echo "Wrote $DOCS_DIR/openapi.json (from $SOURCE_REPO)"
}

case "${1:-build}" in
  build) build ;;

  check)
    # Regenerates into a temporary file and compares, so it reports drift the
    # same way on a developer machine and in CI, with or without local Python.
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' EXIT
    build_to "$tmp"
    if diff -q "$tmp" "$DOCS_DIR/openapi.json" >/dev/null 2>&1; then
      echo "$DOCS_DIR/openapi.json matches the current routes."
    else
      echo "$DOCS_DIR/openapi.json is out of date with the route table."
      echo "Run: sh docs.sh build"
      exit 1
    fi
    ;;

  diagram)
    # Rebuilds the architecture page from diagrams/easy-funnel.architecture.json
    # with the Archify skill, which verifies every cited source path against the
    # pinned revision before it renders. Point ARCHIFY_HOME elsewhere if the
    # skill is not installed under the default Claude skills directory.
    archify="${ARCHIFY_HOME:-$HOME/.claude/skills/archify}"
    if [ ! -f "$archify/bin/archify.mjs" ]; then
      echo "Archify not found at $archify"
      echo "Install the skill, or set ARCHIFY_HOME to its directory."
      exit 1
    fi
    if [ ! -d "$SOURCE_REPO/.git" ]; then
      echo "Production repository not found at $SOURCE_REPO"
      echo "Set SOURCE_REPO to its checkout."
      exit 1
    fi
    node "$archify/bin/archify.mjs" deliver architecture "$PWD/diagrams/easy-funnel.architecture.json" "$PWD/$DOCS_DIR/architecture.html" --quality showcase --repo-root "$SOURCE_REPO"
    node "$archify/bin/archify.mjs" visual-check "$PWD/$DOCS_DIR/architecture.html"
    # visual-check writes screenshots and a receipt beside the artifact. They are
    # evidence, not part of the site, so they are moved out of the directory that
    # gets deployed.
    mkdir -p diagrams/evidence
    mv "$DOCS_DIR"/architecture.visual-check.* diagrams/evidence/ 2>/dev/null || true
    echo "Evidence in diagrams/evidence/"
    ;;

  serve)
    [ -f "$DOCS_DIR/openapi.json" ] || build
    echo "Reference: http://localhost:$PORT"
    echo "(Ctrl-C to stop)"
    cd "$DOCS_DIR" && python -m http.server "$PORT" --bind 127.0.0.1
    ;;

  vercel)
    [ -f "$DOCS_DIR/openapi.json" ] || build
    # Deploys the directory as-is. vercel.json inside it supplies the headers,
    # so there is no build step and no framework to detect.
    cd "$DOCS_DIR" && npx --yes vercel deploy --prod
    ;;

  pages)
    [ -f "$DOCS_DIR/openapi.json" ] || build
    # Cloudflare Pages is the right product for a static site: it serves
    # index.html at the root, honours the _headers file, and gives the project
    # a URL immediately.
    npx --yes wrangler pages deploy "$DOCS_DIR" --project-name "$PROJECT"
    ;;

  r2)
    # R2 is object storage, not a static host. It has no index document, so a
    # bucket serves /index.html but not /, and the _headers file does nothing.
    # Use it only if the bucket is already fronted by a Worker or a custom
    # domain that supplies index resolution; otherwise prefer `pages`.
    : "${R2_BUCKET:?Set R2_BUCKET to the destination bucket name}"
    [ -f "$DOCS_DIR/openapi.json" ] || build
    for file in index.html architecture.html openapi.json; do
      case "$file" in
        *.html) type=text/html ;;
        *.json) type=application/json ;;
      esac
      npx --yes wrangler r2 object put "$R2_BUCKET/$file" \
        --file "$DOCS_DIR/$file" --content-type "$type"
    done
    echo "Uploaded to r2://$R2_BUCKET (remember: / will not resolve to /index.html)"
    ;;

  *)
    echo "usage: sh docs.sh [build|diagram|check|serve|vercel|pages|r2]"
    exit 1
    ;;
esac
