# Backend Development

## Stack

- **Framework**: FastAPI with Python 3
- **ORM**: Prisma Client Python
- **Database**: Neon PostgreSQL (managed)
- **Cache**: Upstash Redis (managed)
- **Image Processing**: Pillow
- **Storage**: Cloudflare R2 (object storage)
- **GeoIP**: MaxMind GeoLite2 (self-hosted, bundled)
- **Deployment**: Single Docker container on Koyeb

## Architecture Principles

### Keep Endpoints Thin

FastAPI routers handle parse/authorize → call service → map result. Business rules belong in `domains/` and `services/`.

```python
# ✓ Good
@router.post("/orders")
async def create_order(payload: OrderCreate, ip: str):
    result = await order_service.submit(payload, ip)
    return result

# ✗ Bad — business logic in route handler
@router.post("/orders")
async def create_order(payload: OrderCreate):
    if not payload.phone.startswith("+57"):
        # ... normalization logic in router
    # ... fraud checks in router
```

### Typed Schemas at Every Boundary

Use Pydantic models for all API requests/responses. Never expose Prisma models directly.

```python
# ✓ Good
class OrderResponse(BaseModel):
    id: str
    status: OrderStatus
    created_at: datetime

# ✗ Bad — exposing ORM model
return order  # Prisma model
```

### Server-Side Validation Always

Validate server-side even when the SPA validates. Define concrete limits for strings, quantities, prices, upload size, and media types.

### Money and Time

- Use `Decimal` and PostgreSQL `numeric` for money (never binary float)
- Store timestamps in UTC; return ISO 8601 with timezone offsets

## Database Conventions

### Migrations

- Every schema change requires a checked-in Prisma migration
- Never rely on ORM auto-create in deployed environments
- Never edit a deployed migration; create a corrective migration instead

```bash
# Create migration
prisma migrate dev --name add_fraud_flags

# Apply in production (one-off controlled step)
prisma migrate deploy
```

### Constraints

Use database constraints for invariants:
- Unique SKU, unique landing slug
- One landing per product
- Valid statuses (enums)
- Required foreign keys

### Transactions

Define transaction boundaries for:
- Order fraud evaluation + persistence (atomic classification)
- Order status transitions
- Duplicate/rate-limit behavior that must not race

```python
# ✓ Good — atomic order + fraud flags
async with prisma.tx() as tx:
    order = await tx.order.create(data)
    if flags:
        await tx.fraud_flag.create_many(flags)
```

## Order Submission Flow

**Critical**: Order submission must be explicit and atomic.

1. Validate → normalize all fields
2. Capture attribution (product, landing) + request metadata (IP, user agent)
3. Run **all** fraud checks synchronously (duplicate, blacklist, rate-limit, GeoIP)
4. Persist **once** in single transaction: `pending` or `flagged_fraud`

Fraud failures are data, not dropped requests. Preserve all triggered flags in machine-readable format.

## Fraud Prevention

### Rate Limiting

- Use Upstash Redis atomic sliding-window counters
- Independent limits for phone and IP
- Default: 5 attempts per 10 minutes
- Count consistently; test transaction/concurrency boundaries

### Duplicate Detection

- Configurable match fields (default: phone + IP)
- Configurable window (default: 24 hours)
- Test exact time boundaries

### Manual Blacklist

- Normalize Colombian phones before matching
- Store reason + timestamp per entry
- Provide add/remove operations

### GeoIP Rules

- Both `flag` and `block` actions produce reviewable `flagged_fraud` orders in v1
- Never silently drop submissions
- Handle unavailable database gracefully

### Configuration

Keep duplicate-match fields and thresholds configuration-driven. Store fraud configuration in database with audit trail.

## Security Rules

### Sensitive Data

Treat names, phones, addresses, IPs, user agents, and order/fraud details as sensitive customer data.

### Authentication & Authorization

- Require authentication for every admin API and CSV export
- Server-side authorization is authoritative (never trust client)
- Hash passwords with memory-hard algorithm (bcrypt/argon2)
- Use short-lived signed JWTs with issuer/audience/expiry validation

### Input Validation

- Validate and normalize Colombian phones consistently
- Use parameterized Prisma queries (no SQL from user input)
- Apply rate limits to login and order submission
- Validate image format/size/dimensions before processing

### Output Safety

- Return stable error codes + field-specific details where safe
- Never return stack traces or database details
- Use structured logs; redact passwords, JWTs, credentials, full addresses
- Escape CSV export values to prevent formula injection

### Audit Trail

Record local audit entries for:
- Login/security events
- Admin mutations to fraud settings, blacklists
- Product availability changes
- Landing publication changes
- Order status transitions

## Image Pipeline

### Upload Validation

1. Accept only explicit allowlist: JPEG, PNG, WebP
2. Enforce byte-size and pixel-dimension limits before expensive work (max 10 MiB)
3. Decode and validate dimensions (480-8000px width, 1-8000px height, max 40M total pixels)

### Processing

1. Strip EXIF metadata (privacy)
2. Generate WebP + JPEG variants for configured widths: 480, 768, 1200, 1600
3. Never upscale past source width
4. Use opaque storage identifiers (no client filenames)
5. Write variants atomically; remove partial files on failure
6. Extract the top/bottom edge colors and persist them on `image_assets`

### Banner Edge Colors and CTA Bands

The CTA band rendered between two banners is painted from the banner edges it
sits against, so it reads as part of the artwork.

Split of responsibility:

- **Upload time** (`app/domains/images/edge_color.py`): sample a thin strip at
  each edge of the already-decoded source and store `top_edge_color`,
  `bottom_edge_color`, plus `*_edge_flat` flags on `image_assets`. Statistics
  come from Pillow's C-level histogram and channel means are averaged in
  linear light, so the cost is fixed regardless of image size.
- **Read time** (`app/domains/landings/cta_background.py`): blend the bottom
  edge of the banner above with the top edge of the banner below into one
  band descriptor per CTA position.

The blend is **not** persisted. Its inputs depend on banner order, `cta_mode`,
`cta_interval`, and `cta_positions`, all of which change without any upload, so
a stored blend would need invalidating on every reorder. Recomputing is
arithmetic on two hex strings — no image access, no I/O.

Consumers get gradient endpoints (`top_color`, `bottom_color`), the solid-fill
equivalent (`blend_color`), and a `foreground` hint (`light`/`dark`) derived
from the band's WCAG relative luminance so the CTA button never lands on a
band of matching lightness. A band is returned as `source: "fallback"` with
null colors — the client's neutral token — only when neither neighbouring
banner has a stored edge color at all.

**Gradient or solid** is a per-landing choice, `landings.cta_band_style`
(`gradient` default, or `solid`), validated by
`app/domains/landings/cta_band_style.py` against the
`landings_cta_band_style_allowed` check. It is carried on the public payload
and changes nothing about the band descriptors: `solid` means the client paints
`blend_color` across the whole band instead of running the gradient. Deriving
different colors per style would put one decision in two places, so the
backend does not. Which style suits a sequence depends on how far apart the
neighbouring edges are, which is a judgement about the artwork — hence a
merchant setting rather than a computed one.

`*_edge_flat` is diagnostic and gates nothing. A busy edge still paints its
mean: the mean minimises error against its own strip by construction, so the
neutral is weakly worse for every edge, and its error is the visible kind (a
full-width band of unrelated lightness between two full-bleed photos looks
broken). Full-resolution strips of real product photography rarely pass a
flatness test, so gating on the flag meant the band was almost always neutral.

Assets created before edge extraction existed have null colors. Backfill them
with `python -m scripts.backfill_edge_colors` (supports `--dry-run`,
`--limit`, `--force`); it re-reads each source object from R2 once and never
re-encodes or re-uploads anything.

### Storage

- Upload to Cloudflare R2 under opaque keys
- Use versioned immutable URLs for long cache lifetimes
- Orphan cleanup: derive liveness from database references, be idempotent

## Colombian Phone Normalization

Colombian mobile numbers normalize to `+57` followed by 10 digits where the national number begins with `3`.

Input may contain:
- `+57` or `57` country code
- Spaces, hyphens, parentheses

Normalization must be idempotent: `normalize(normalize(x)) == normalize(x)`.

Use the same normalization for duplicate detection, blacklist matching, and rate limiting.

## Error Handling

- Field-specific validation: return 422 with field errors
- Not found: return 404 (but use identical behavior for unknown, draft, and paused landings to avoid information disclosure)
- Server errors: return 503/500 generic (no stack traces)
- Preserve attempted order data even on fraud triggers

## Testing Requirements

Backend tests must cover:

- Product constraints, one-landing invariant, publication/paused behavior
- Slug uniqueness, banner ordering, CTA placement calculations, 1-15 banner boundaries
- Colombian phone normalization/validation, all order field boundaries
- Every legal and illegal order-status transition
- Duplicate windows at exact time boundaries, configurable match-field combinations
- Manual blacklist normalization/add/remove
- Independent phone/IP rolling rate limits, exact threshold boundaries, concurrent attempts
- GeoIP match, unknown IP, unavailable database, block/flag configuration
- Atomic order classification: every valid submission → exactly one `pending` or `flagged_fraud` order
- Authentication expiry/tampering, authorization, audit records, secret redaction, CSV injection defense
- Image format/size/pixel validation, EXIF stripping, variant generation, non-upscaling, cleanup

## Deployment

Backend runs as a single stateless FastAPI container on Koyeb:

```dockerfile
# Dockerfile (example structure)
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
COPY prisma/ prisma/
RUN prisma generate
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Environment variables (never commit actual values). `app/core/settings.py` is
the single source of truth for the exact names; `.env.example` documents them
with safe placeholders:
- `DATABASE_URL` (Neon connection string)
- `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` (Upstash REST API)
- `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_HOST`
- `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRY_MINUTES`, `JWT_ISSUER`, `JWT_AUDIENCE`
- `GEOIP_DATABASE_PATH`

GeoLite2 database ships inside the image; refresh via in-instance scheduled task with validate-before-activate logic.
