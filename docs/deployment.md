# Deployment

## Cloud-Native Architecture

The COD Commerce Platform runs entirely on managed cloud services. There is no Docker Compose, no VPS, no Nginx, no persistent local volumes, and no custom backup scripts.

### Infrastructure Components

- **Cloudflare Pages**: Builds and serves the React+Vite SPA (public storefront + private admin)
- **Cloudflare DNS**: Routes public traffic to Pages (SPA) and Koyeb (backend API)
- **Cloudflare R2**: Object storage for source images and generated variants
- **Koyeb**: Managed container platform running a single FastAPI Docker container
- **Neon PostgreSQL**: Managed PostgreSQL with automated backups
- **Upstash Redis**: Managed Redis for rate limiting, counters, temporary state, caching

### Request Routing

```
User → Cloudflare DNS
  ├─ / , /p/:slug , /admin/* → Cloudflare Pages (SPA)
  └─ /api/* → Koyeb backend (FastAPI)

User → Image URLs → Cloudflare R2 (direct, immutable cache)
```

### What's NOT Deployed

- Docker Compose
- Nginx or reverse proxy container
- PostgreSQL container
- Local persistent volumes
- Custom pg_dump backup jobs
- VPS or self-managed servers

## Backend Deployment (Koyeb)

### Docker Container

Backend runs as a single stateless FastAPI container:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ backend/
COPY prisma/ prisma/

# Generate Prisma client
RUN prisma generate

# Expose port
EXPOSE 8000

# Run FastAPI with uvicorn
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Environment Variables

**Never commit actual values.** Use Koyeb environment variable configuration.

Required variables (exact names come from `app/core/settings.py`; see
`.env.example`):
- `DATABASE_URL` (Neon connection string with SSL)
- `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` (Upstash REST API)
- `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_HOST`
- `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRY_MINUTES`, `JWT_ISSUER`, `JWT_AUDIENCE`
- `GEOIP_DATABASE_PATH`
- `CLOUDFLARE_ACCOUNT_ID` (if needed for R2 access)

### Deployment Process

1. Build Docker image (pinned version, not `latest` tag)
2. Push to container registry (Koyeb or Docker Hub)
3. Deploy to Koyeb with environment variables
4. Run database migrations as one-off task: `prisma migrate deploy`
5. Verify health endpoint, public landing, admin login, COD submission

### Health Check

Backend must expose a health endpoint for Koyeb monitoring:

```python
@app.get("/health")
async def health():
    return {"status": "healthy", "version": os.getenv("APP_VERSION")}
```

### GeoIP Database

GeoLite2 database ships inside the Docker image. Refresh via in-instance scheduled task:

1. Download new database
2. Validate (test basic resolution)
3. Atomic activation (swap active file)
4. Preserve last known-good file on validation failure

No runtime geolocation API dependency.

## Frontend Deployment (Cloudflare Pages)

### Build Configuration

Cloudflare Pages builds and deploys the SPA automatically on push.

**Build settings:**
- Build command: `pnpm --prefix frontend run build`
- Output directory: `frontend/dist`
- Node version: 18 or later

### SPA Fallback Routing

Configure fallback to serve `index.html` for all routes except `/api`:

```toml
# wrangler.toml or Cloudflare Pages configuration
[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

Cloudflare DNS routes `/api/*` to the Koyeb backend.

### Build-Time Variables

Frontend build-time variables should **not** contain secrets. Only publicly visible values (e.g., `VITE_API_BASE_URL` if needed).

### Deployment Process

1. Push to `main` branch (or configured branch)
2. Cloudflare Pages triggers build automatically
3. Build runs `pnpm --prefix frontend run build`
4. Static assets deployed to Cloudflare edge
5. Verify SPA loads, routing works, API calls reach backend

## Database (Neon PostgreSQL)

### Managed Backups

Neon provides automated backups. Verify backup schedule and retention in Neon dashboard.

### Migrations

Apply migrations as a **one-off controlled step**, not from every app process:

```bash
# Before deploying new application version
prisma migrate deploy
```

**Critical:** Take and verify a backup before production migrations.

### Migration Testing

Before production migration:
1. Test migration against empty database
2. Test migration from previous release schema with synthetic data
3. Test restore from backup

### Rollback

- Roll application images back on failure
- Do **not** run destructive database rollback unless the migration has an explicitly tested safe downgrade and a current backup

## Image Storage (Cloudflare R2)

### Bucket Configuration

- Bucket: one R2 bucket for all images
- Access: backend uploads via R2 API; public reads via Cloudflare public URL
- Cache: immutable long-lived `Cache-Control` headers

```
Cache-Control: public, max-age=31536000, immutable
```

### Object Keys

Use opaque, versioned keys to avoid collisions:

```
/originals/{opaque_id}.{ext}
/variants/{opaque_id}/{width}.{webp|jpg}
```

### Public Access

Images served directly from R2 through Cloudflare. Backend is **not** in the hot image path.

## Cache (Upstash Redis)

### Usage

- Rate-limit counters (rolling windows)
- Fraud counters (duplicate detection, attempt tracking)
- Temporary session state
- Caching computed values

### Ephemeral Nature

Redis counters are best-effort. The durable order and fraud record is always in PostgreSQL.

### Connection

Use `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` from the
environment. Upstash serves counters over its HTTPS REST API, which is what
`app.redis.client` talks to.

## Deployment Discipline

### Pinned Versions

- Pin production container images to reviewed versions (never `latest`)
- Pin application dependencies to exact versions in `requirements.txt` / `pnpm-lock.yaml`

### Pre-Deployment Checklist

1. All tests pass (backend + frontend)
2. Production build succeeds
3. Migration tested (if schema changed)
4. Environment variables configured
5. Backup verified (if database changes)

### Deployment Steps

1. **Backup**: Verify Neon automated backup or take manual backup
2. **Migrate**: Run `prisma migrate deploy` as one-off task
3. **Deploy Backend**: Deploy pinned container image to Koyeb
4. **Deploy Frontend**: Push to Cloudflare Pages (auto-build)
5. **Verify**: Test health endpoint, public landing, admin login, COD submission, fraud classification, image serving

### Post-Deployment Verification

- Health endpoint responds
- Public landing loads (`/p/{slug}`)
- Admin login works
- COD form submission creates order
- Fraud checks apply correctly
- Images load from R2
- Persistent data survives deployment (check database, R2)

### Rollback

1. Roll application images back to previous version
2. Do **not** run destructive database rollback without:
   - Explicitly tested safe downgrade
   - Current verified backup
   - Production data preservation

### Deployment Notes

Keep deployment notes for:
- Schema version
- Application image versions (backend, frontend)
- Environment variable changes
- Backup result
- Health verification result
- Rollback point

## Security Configuration

### TLS

- Cloudflare provides TLS for all public traffic
- Koyeb provides TLS for backend
- Neon/Upstash connections use TLS

### Secrets Management

- Never commit secrets to Git
- Use Koyeb environment variables for backend secrets
- Use Neon/Upstash dashboard for connection strings
- Rotate JWT secrets, R2 credentials periodically

### Network Isolation

- Neon and Upstash endpoints are **not** publicly exposed
- Only Cloudflare Pages and Koyeb backend URL receive public traffic
- Backend API requires authentication for admin endpoints

## Monitoring and Operations

### Operational Interface

Backend exposes read-only operational interface (authenticated):
- Service health state
- Deployed application version
- Backup status (success/failure + timestamp)
- GeoIP update status (success/failure + timestamp)
- Image cleanup status (success/failure + timestamp)

**Excludes:** customer data, credentials, JWTs, database connection data, filesystem paths, request payloads, logs, diagnostic stacks.

### Health Monitoring

Configure Koyeb to monitor `/health` endpoint and restart on failure.

### Logs

- Structured logs from backend
- Redact passwords, JWTs, credentials, full addresses
- Use Koyeb logs for debugging
- Cloudflare Pages build logs for frontend issues

## Excluded Infrastructure

Do **not** add in v1:
- PgBouncer or database connection pooling
- Kubernetes or multi-node orchestration
- Read replicas
- Horizontal autoscaling
- Message brokers or event buses
- Additional external SaaS beyond Cloudflare, Koyeb, Neon, Upstash

Keep the deployment simple and maintainable.
