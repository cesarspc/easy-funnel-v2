# Easy Funnel

A lightweight commerce platform for selling physical products through dedicated landing pages. Built for a single merchant managing multiple product funnels from one admin panel.

## What it does

Each product gets its own banner-based landing page. A visitor arrives (usually from a paid ad), sees the product banners, clicks the call-to-action, fills out a short order form, and the order appears in the admin dashboard — ready for fulfillment. Server-side fraud checks run automatically before any order is effectively accepted.

## Architecture

| Layer | Tech | Deployed on |
|-------|------|-------------|
| Frontend | React + Vite (SPA) | Cloudflare Pages |
| Backend | FastAPI (single container) | Railway |
| Database | PostgreSQL | Neon |
| Cache & Counters | Redis | Upstash |
| Image Storage | Object storage | Cloudflare R2 |
| GeoIP | MaxMind GeoLite2 | Bundled in container |
| COD Fulfillment | Order handoff | MasterShop |

Monolithic backend by design — no microservices. MasterShop is the single
post-commit fulfillment integration; local order acceptance never depends on
its availability.

## Project Structure

```
├── frontend/          React SPA (pnpm)
├── backend/           FastAPI application (pip)
├── prisma/            Database schema & migrations
├── infrastructure/    Deployment configs (Railway, Cloudflare, R2, GeoIP)
├── docs/              Developer documentation
└── docker-compose.yml Local test services (Postgres + Redis)
```

## Quick Start

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

For MasterShop fulfillment, deploy the additive Prisma migration first with
`MASTERSHOP_API_KEY` unset, configure each product/variant mapping in Admin,
and only then add the key to the backend secret manager. Existing orders are
not backfilled; orders created during the staged rollout retain a failed sync
record that can be reviewed and retried from Admin.

## Documentation

- [Backend Development](docs/backend.md) — API structure, domains, services, fraud logic, security
- [Frontend Development](docs/frontend.md) — Components, routing, mobile-first patterns, accessibility
- [Testing Strategy](docs/testing.md) — Property-based testing, validation, CI
- [Deployment](docs/deployment.md) — Cloudflare Pages, Koyeb, backups, rollback

## Key Design Decisions

- **No storefront or catalog** — each product lives at its own URL (`/p/{slug}`), reached via direct links from ads or social
- **Local order authority** — images, GeoIP, fraud rules, and accepted orders remain local; fulfillment handoff failures are durable and retryable
- **Single admin role** — one merchant operates the entire platform
- **Mobile-first public pages** — buyers come from ads on their phones
- **Desktop-first admin** — the dashboard is an operational tool for daily use

## License

Private — all rights reserved.
