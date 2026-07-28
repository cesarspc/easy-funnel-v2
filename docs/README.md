# Documentation Structure

This directory contains focused, specialized documentation following the principle of **progressive disclosure**. The root `AGENTS.md` remains minimal and references these files for detailed guidance.

## Files

### [backend.md](backend.md)
**Backend development guidance** — FastAPI architecture, Prisma ORM patterns, fraud prevention logic, order submission flow, security rules, Colombian phone normalization, image pipeline, audit trails, and backend testing requirements.

**Use when:** Working on FastAPI routes, services, domains, fraud logic, database schema, migrations, image processing, or backend security.

### [frontend.md](frontend.md)
**Frontend development guidance** — React + TypeScript patterns, SPA routing, mobile-first design, responsive images, COD form modes, admin dashboard, accessibility, and frontend testing requirements.

**Use when:** Working on React components, public landings, COD forms, admin UI, routing, or frontend accessibility/performance.

### [testing.md](testing.md)
**Testing strategy and validation** — Property-based testing with Hypothesis and fast-check, required properties, validation commands, integration tests, pre-merge checklist, and CI requirements.

**Use when:** Writing tests, setting up property-based tests, running validation commands, or preparing for merge/CI.

### [deployment.md](deployment.md)
**Cloud deployment and operations** — Koyeb backend container, Cloudflare Pages frontend, Neon PostgreSQL, Upstash Redis, R2 image storage, migration discipline, health monitoring, rollback procedures, and security configuration.

**Use when:** Deploying to production, configuring infrastructure, running migrations, troubleshooting deployment issues, or setting up monitoring.


### Root AGENTS.md Contains Only:
- One-sentence project description
- High-level architecture (2 apps, cloud services)
- Package managers
- Source of truth references (`features.json`, `requirements.md`)
- What's excluded from v1
- Links to specialized documentation

### Specialized Docs Contain:
- **Concepts** — architectural decisions, responsibilities, patterns
- **Constraints** — hard rules that must be followed
- **Guidance** — how to implement correctly
- **Examples** — good vs. bad patterns
- **Testing requirements** — specific to that area

### NOT Documented:
- File structure (becomes stale, obvious from code)
- Generic programming advice (already known by modern agents)
- Obvious practices (redundant)
- Business rules (those live in `requirements.md`)

## Using This Documentation

1. **Starting a task?** Read `AGENTS.md` first (should take 1-2 minutes)
2. **Working on backend?** Open `docs/backend.md` for detailed guidance
3. **Working on frontend?** Open `docs/frontend.md` for React/TypeScript patterns
4. **Writing tests?** Check `docs/testing.md` for property-based testing and validation commands
5. **Deploying?** Follow `docs/deployment.md` for cloud infrastructure and migration discipline

Each document is self-contained but cross-references others when needed.
