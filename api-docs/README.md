# Easy Funnel backend documentation

A self-contained static site. It calls nothing, and **the backend does not need
to be running** — not to view it, not to build it, and not to deploy it.

| Route | What it is |
| --- | --- |
| `/` | API reference, rendered from `openapi.json`. |
| `/architecture` | System architecture diagram: components, boundaries and the paths between them. |
| `/openapi.json` | The OpenAPI 3.1 document itself, for any other tool. |

| File | What it is |
| --- | --- |
| `openapi.json` | Generated from the live route table. |
| `index.html` | Renders the reference in the browser. |
| `architecture.html` | The diagram, fully self-contained — no external requests at all. |
| `vercel.json` / `_headers` | Content type, caching and CORS, one per host. |

## Build

```sh
sh docs.sh build      # writes api-docs/openapi.json
sh docs.sh diagram    # writes api-docs/architecture.html
sh docs.sh serve      # preview at http://localhost:8099
```

The preview server has no clean-URL resolution, so the diagram is at
`/architecture.html` locally and at `/architecture` once published; both hosts
redirect the file path to the clean route.

`build` derives the document from the imported application object, so no server
starts and no database, cache or object store is contacted. It uses the local
Python environment when the backend's dependencies are installed there, and
otherwise falls back to the backend image — which means it works on a machine
with nothing but Docker.

## Publish

```sh
sh docs.sh pages      # Cloudflare Pages  (recommended)
sh docs.sh vercel     # Vercel
```

Both deploy this directory as-is. There is no build step, no framework to
detect, and no environment variable to set.

The first run of each asks you to sign in and pick a project; every run after
that is just the command. Override the Pages project name with
`PAGES_PROJECT=my-name sh docs.sh pages`.

### About Cloudflare R2

R2 is object storage, not a static host. A public R2 bucket serves
`/openapi.json` and `/index.html`, but it has **no index document**, so the bare
`/` does not resolve and the `_headers` file is ignored. Use Pages unless the
bucket already sits behind a Worker or a custom domain that supplies index
resolution.

If you need it anyway:

```sh
R2_BUCKET=my-bucket sh docs.sh r2
```

## Keeping it honest

Both pages are generated, never edited by hand — edits to `openapi.json` or
`architecture.html` are overwritten by the next build. To change what they say,
change the source:

- Endpoint summary and description come from the route's `summary=` and its
  docstring.
- Request and response schemas come from the Pydantic models.
- The introduction, tag descriptions and security scheme live in
  `backend/app/api/openapi.py`.
- The diagram is compiled from `diagrams/easy-funnel.architecture.json`.

The diagram spec pins a commit and cites a source file for each component.
Archify verifies every cited path exists at that revision before it will render,
so a node cannot quietly claim to represent code that is not there. Source links
are set to `local-only`, so the published page names the files without emitting
links to the repository.

CI can assert the committed document still matches the routes:

```sh
sh docs.sh check      # non-zero exit if it is stale
```

## What is intentionally missing

Only endpoints backed by a working implementation are published. One operational
endpoint (`GET /api/admin/ops/jobs`) is excluded, because it currently returns a
fixed structure of nulls — the background tasks it reports on exist, but nothing
records their results yet. It is hidden with `include_in_schema=False` and
carries a comment explaining what has to be true before it is published.
