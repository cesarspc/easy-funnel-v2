# COD Commerce Platform

A lightweight, cloud-native commerce platform for low-ticket physical products sold cash on delivery (COD / contraentrega) in Colombia.

## Core Flow

Every feature must map directly to: **banner landing → CTA → COD form → fraud check → order in admin**.

If a feature does not serve this flow, it does not belong in v1.

## Architecture

- **Frontend**: React + Vite SPA deployed on Cloudflare Pages
- **Backend**: FastAPI (single Docker container) deployed on Koyeb
- **Database**: Neon PostgreSQL via Prisma ORM
- **Cache/Counters**: Upstash Redis
- **Images**: Cloudflare R2
- **GeoIP**: Self-hosted MaxMind GeoLite2 (bundled in container)

This is intentionally **not** a microservices architecture. The backend is one deployable application.

## Package Managers

- **Frontend**: `pnpm` (commands run with `pnpm --prefix frontend run <script>`) DONT USE npm
- **Backend**: `pip` via `requirements.txt` or `pyproject.toml`
- **Database**: Prisma CLI for migrations (`prisma migrate`)

## Source of Truth

- **`features.json`**: Product requirements and scope
- **`.kiro/specs/cod-commerce-platform/requirements.md`**: Complete P0 contract

Do not duplicate business rules, acceptance criteria, or feature specifications in code or documentation. Reference requirements.md when detailed functional behavior is needed.

## What's NOT in v1

Online payment gateways • multi-currency • multi-language • drag-and-drop builders • theme marketplaces • app marketplaces • subscriptions • multi-warehouse routing • POS • external CDN (beyond Cloudflare) • paid image transformation SaaS • SSR/Next.js • fraud notification alerts • PgBouncer • Kubernetes • horizontal scaling

These stay out of v1 by default. If work genuinely needs one, don't block waiting for approval — implement the smallest version that unblocks the task, note the assumption in the change summary, and move on.

## Documentation

Detailed guidance by area:

- **[Backend Development](docs/backend.md)** — FastAPI, Prisma, domains, services, fraud logic, security, audit
- **[Frontend Development](docs/frontend.md)** — React, TypeScript, routing, mobile-first design, accessibility
- **[Testing Strategy](docs/testing.md)** — Property-based testing, validation commands, CI requirements
- **[Deployment](docs/deployment.md)** — Cloud deployment, Koyeb, Cloudflare, backups, rollback

## Working Rules

- Read requirements.md, and nearby code before modifying behavior
- Implement approved P0 requirements end-to-end, including whatever dependencies, endpoints, fields, or services that requires — don't stop to ask, use judgment, stay inside the Core Flow
- Never add external CDN/SaaS/runtime third-party dependencies beyond the stack already listed in Architecture
- Keep secrets, uploads, database volumes, and local environment files out of Git
- Update tests and documentation in the same change as behavior
- Run validation and report exact commands/results
- Default to full autonomy — proceed without asking for anything reversible (code, config, schema changes via migrations, dependencies, tests, docs).

### The only things worth stopping for

Pause and confirm only before actions that are destructive or hard to undo:
- Deleting or truncating data outside a reviewed migration
- Dropping tables/databases, or running migrations against production
- Force-pushing, rewriting git history, or deleting branches
- Wiping local env files, volumes, or uncommitted work
- Touching production secrets/credentials, or anything outside this project's directory

If All is in development environment its ok.

Everything else: just do it.