# Easy Funnel

A lightweight commerce platform for selling physical products through dedicated landing pages. Built for a single merchant managing multiple product funnels from one admin panel.

## What it does

Each product gets its own banner-based landing page. A visitor arrives (usually from a paid ad), sees the product banners, clicks the call-to-action, fills out a short order form, and the order appears in the admin dashboard — ready for fulfillment. Server-side fraud checks run automatically before any order is effectively accepted.

## Architecture

| Layer | Tech | Self-hosted service |
|-------|------|-------------|
| Frontend/proxy | React + Vite (SPA) | Caddy container |
| Backend | FastAPI monolith | Application container |
| Database | PostgreSQL | PostgreSQL container |
| Cache & Counters | Redis | Redis container |
| Image Storage | S3-compatible objects | MinIO container |
| GeoIP | MaxMind GeoLite2 | Bundled in container |
| COD Fulfillment | Optional order handoff | Disabled or MasterShop |

Monolithic backend by design — no multi-tenancy and no microservices. When
enabled, MasterShop runs after the local order commit; order acceptance never
depends on its availability.

## Project Structure

```
├── frontend/          React SPA (pnpm)
├── backend/           FastAPI application (pip)
├── prisma/            Database schema & migrations
├── infrastructure/    Deployment configs (Railway, Cloudflare, R2, GeoIP)
├── docs/              Developer documentation
└── docker-compose.yml Complete production-like self-hosted stack
```

## Self-hosted quick start

The supported deployment is a reproducible Docker Compose stack containing
Caddy, the React application, FastAPI, PostgreSQL, Redis, and MinIO.

```bash
cp docker.env.example .env
# Replace every password/secret placeholder and customize STORE_* values.
docker compose up --build -d
docker compose ps
```

The local defaults expose the store on `http://localhost:8088`, PostgreSQL on
`5433`, Redis on `6380`, and the MinIO console on `9003`. For a public server,
set `APP_SITE_ADDRESS` to the real domain, `APP_PUBLIC_URL` to its HTTPS URL,
`HTTP_PORT=80`, `HTTPS_PORT=443`, and `ACME_EMAIL`; Caddy obtains and renews
TLS automatically.

Store values initialize the database only once. Afterwards the merchant edits
branding, homepage content, assets, contact information, SEO, tracking IDs,
market conventions (country, locale, currency, time zone, phone calling code
and national-number pattern) and the fulfillment integration (provider, URL,
timeout, write-only API key) under **Admin → Tienda**; restarting containers
does not revert those edits.

Infrastructure wiring in `docker-compose.yml` (database/Redis/S3 URLs, bucket
name, JWT parameters, internal ports, Caddy upstreams, GeoIP paths) is also
overridable from `.env`; the optional block at the end of `docker.env.example`
lists every knob with its default.

### Clean database verification

The following command creates a disposable PostgreSQL 16 database exposed on
port `55433` (separate from both the normal stack and the legacy `55432` test
port), validates and tests the frontend image, applies every migration from
zero, and runs the backend suite inside the built application image:

```bash
sh test-fresh.sh
```

The script always removes its isolated containers and volumes when it exits,
so repeated runs prove a clean installation rather than reusing database state.

## Developer quick start

### Prerequisites

- Node.js 20+ and pnpm
- Python 3.12+
- Docker (for local database and Redis)

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate  # or source .venv/bin/activate on Linux/macOS
pip install -r requirements.txt -r requirements-dev.txt

# Copy and configure environment
cp ../.env.example .env

# Start test services
docker compose up -d

# Run migrations
npx prisma migrate dev --schema ../prisma/schema.prisma

# Start the server
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

The dev server starts at `http://localhost:5173` and proxies `/api` calls to the backend on port 8000.

### Running Tests

```bash
# Backend
cd backend
pytest

# Frontend
cd frontend
pnpm test
```

## Environment Variables

Copy `.env.example` to `.env` and fill in your values. The example file documents every variable with placeholder values. Frontend build-time variables (prefixed `VITE_`) contain no secrets — only public configuration like the API base URL.

For MasterShop fulfillment, configure each product/variant mapping in Admin,
then set the provider, orders URL and API key under **Admin → Tienda**. The
`FULFILLMENT_PROVIDER` / `MASTERSHOP_*` variables only seed those settings the
first time a database starts without them. Existing orders are
not backfilled; orders created during the staged rollout retain a failed sync
record that can be reviewed and retried from Admin.

## Documentation

- [Backend Development](docs/backend.md) — API structure, domains, services, fraud logic, security
- [Frontend Development](docs/frontend.md) — Components, routing, mobile-first patterns, accessibility
- [Testing Strategy](docs/testing.md) — Property-based testing, validation, CI
- [Deployment](docs/deployment.md) — Cloudflare Pages, Koyeb, backups, rollback

## Key Design Decisions

- **Brand homepage, no catalog** — the root represents the merchant while each product lives at its own direct URL (`/p/{slug}`)
- **Local order authority** — images, GeoIP, fraud rules, and accepted orders remain local; fulfillment handoff failures are durable and retryable
- **Single admin role** — one merchant operates the entire platform
- **Mobile-first public pages** — buyers come from ads on their phones
- **Desktop-first admin** — the dashboard is an operational tool for daily use

## License

Private — all rights reserved.
