# Testing Strategy

## General Principles

- Every behavior change requires tests at the lowest useful level plus boundary integration coverage
- Bug fixes require a regression test that fails before the fix
- Test boundaries, edge cases, and concurrent behavior
- Use property-based testing for rule-heavy and broad input spaces

## Property-Based Testing

### Python: Hypothesis

Use Hypothesis for backend property tests. Pin exact dependency version.

```python
# ✓ Good example
from hypothesis import given, strategies as st

@given(
    banners=st.lists(st.integers(min_value=1), min_size=1, max_size=15),
    reorder_op=st.tuples(st.integers(min_value=0), st.integers(min_value=0))
)
def test_banner_reorder_is_permutation(banners, reorder_op):
    """For any banner list and valid reorder operation, order indexes are unique
    and the rendered sequence is a permutation of the same banners."""
    from_idx, to_idx = reorder_op
    if from_idx >= len(banners) or to_idx >= len(banners):
        return  # invalid operation
    
    result = reorder_banners(banners, from_idx, to_idx)
    
    assert sorted(result) == sorted(banners)
    assert len(result) == len(set(result))  # all unique
```

### TypeScript: fast-check

Use fast-check for frontend property tests if logic warrants it.

```typescript
import fc from 'fast-check';

test('CTA positions satisfy placement mode', () => {
  fc.assert(
    fc.property(
      fc.integer({ min: 1, max: 15 }),
      fc.constantFrom('every', 'everyN', 'fixed'),
      fc.integer({ min: 1, max: 15 }),
      (bannerCount, mode, interval) => {
        const positions = computeCtaPositions(bannerCount, mode, interval);
        // positions must be within sequence
        positions.every(pos => pos >= 0 && pos <= bannerCount);
        // positions must be sorted
        positions.every((pos, i, arr) => i === 0 || pos > arr[i - 1]);
      }
    )
  );
});
```

## Required Properties

Backend property tests must include:

1. **Banner reordering**: For any banner list and valid reorder operation, order indexes are unique and the rendered sequence is a permutation of the same banners.

2. **CTA placement**: For any valid CTA configuration and 1-15 banner count, generated CTA positions satisfy the selected mode and stay within the sequence.

3. **Phone normalization**: For any accepted phone representation, normalization is idempotent and equivalent representations produce the same duplicate/blacklist key.

4. **Order status transitions**: For any order state and requested transition, only the documented transition graph can change persisted status.

5. **Fraud classification**: For any set of fraud rule outcomes, classification is `pending` exactly when no rule triggers; otherwise classification is `flagged_fraud` and all triggered rule identities are preserved.

6. **Duplicate detection**: For any duplicate-window boundary, only records inside the configured interval with all configured match fields equal trigger duplicate detection.

7. **Rate limiting**: For any attempt stream, rolling-window counts do not include attempts outside the configured interval and trigger at the documented threshold.

8. **Image generation**: For any supported source dimensions, generated widths are from the configured set, are no larger than the source, and preserve aspect ratio within encoding tolerance.

9. **CSV safety**: For any exported customer string, CSV encoding round-trips as data and cannot become an executable spreadsheet formula.

10. **Banner edge colors / CTA bands**: For any solid source image, both extracted edge colors equal that color exactly; for any CTA configuration and stored edge set, every position yields exactly one band whose colors are either all present and valid hex or all absent (fallback). For any string, `validate_cta_band_style` either raises a field-specific error or returns a value inside the allowed vocabulary, which must equal the database check constraint.

Persist discovered counterexamples as focused regression examples.

## Validation Commands

Keep these canonical commands working. Commands must be non-interactive and single-run (no watch mode).

### Backend

```bash
# Linting
python -m ruff check backend

# Formatting
python -m ruff format --check backend

# Type checking
python -m mypy backend/app

# Tests
python -m pytest backend/tests
```

### Test environment

`backend/tests/conftest.py` owns the test environment. It applies synthetic,
tracked placeholders for every `Settings` field the application needs to boot
(Upstash Redis, R2, JWT, GeoIP), so a clean checkout is reproducible and the
suite never depends on a developer's machine. Precedence, highest first:

1. the real process environment (CI secrets, an explicit `DATABASE_URL`)
2. `backend/.env.test`, when present (untracked local overrides)
3. the tracked synthetic defaults

Variable names in `.env.test` must match `app/core/settings.py` exactly — the
application and the tests share one configuration vocabulary.

`DATABASE_URL` is deliberately not defaulted: it must point at a real
throwaway database, and its absence is what makes database-backed tests skip
instead of failing against an imaginary server. Tests that assert on
`Settings` parsing itself clear those variables first, so their result never
depends on the ambient environment.

### Database

Database-backed tests (`backend/tests/db/`, `backend/tests/e2e/`) require a
reachable `DATABASE_URL` and are skipped automatically when it is not set.

> **The suite drops the database it points at.** The migration harness
> (`backend/tests/db/test_migrations.py`) runs `prisma migrate reset --force`,
> which recreates the schema from scratch. Anything in that database — local
> products, landings, banners, and Administrator accounts created with
> `scripts/seed_admin.py` — is erased on every full run. Keep `DATABASE_URL`
> pointed at a disposable database, and use a **different** database in
> `backend/.env` for the development server if you want its data to survive a
> test run.
Start the throwaway containers and export the connection string:

```bash
docker compose up -d          # postgres on 55432, redis on 6379

export DATABASE_URL=postgresql://cod_user:cod_password@localhost:55432/cod_platform_test
python -m prisma migrate deploy --schema=prisma/schema.prisma
python -m pytest backend/tests
```

Postgres is published on 55432 rather than 5432 so it never collides with a
native PostgreSQL install on the host.

### Development data

A finished test run leaves the database empty: the migration harness recreates
the schema and the e2e tests delete what they create. Two scripts fill it back
in for local exploration, and both are safe to re-run:

```bash
# Administrator account (Argon2id hash + audit entry)
$env:ADMIN_PASSWORD = "..."
python -m scripts.seed_admin --username admin        # from backend/

# Catalog, banners, analytics, and orders in every fraud state
python -m scripts.init_local_r2                      # bucket for banner images
python -m scripts.seed_dev_data --username admin
```

`seed_dev_data` drives the real admin and public APIs, so seeded rows obey the
same validation, fraud evaluation, and audit rules as merchant traffic. It
injects the same Redis and GeoIP doubles the e2e tests use (protocol mismatch
and licensed database, above), refuses to run outside `ENVIRONMENT=development`,
and deletes its own `DEV-%` / `%-dev` rows before recreating them. It produces
three published landings, one `pending` order per landing, and one order for
each of the duplicate and blacklist fraud paths.

Run it **after** the test suite, not before: the suite drops the database.

### Redis

The Redis rate-limit tests (`backend/tests/redis/`) run against an in-process
fake (`tests/redis/fakes.py`) and need no external service.

The docker `redis` container speaks the Redis wire protocol while the
application client speaks the Upstash REST API, so tests never point the
application at it. Tests that need working counters inject the same fake
through FastAPI's `dependency_overrides` (see `tests/e2e/conftest.py`), which
also gives each test a clean rolling window. A real Upstash REST endpoint is
only required for manual/exploratory checks against
`app.redis.client.get_redis_client`.

### End-to-end tests

`backend/tests/e2e/` drives the real ASGI application against the real
database. Two collaborators are injected as doubles because neither is
reachable from a test run: Redis (protocol mismatch, above) and GeoIP (the
MaxMind GeoLite2 database is a licensed binary that is not committed).
Everything else — routing, validation, fraud evaluation, persistence, audit,
admin authorization — is exercised for real.

R2 client integration tests (`backend/tests/storage/test_r2_client.py`)
require `R2_TEST_ENDPOINT` and are skipped otherwise. For local runs, start
a throwaway MinIO container (S3-compatible):

```bash
docker run --rm --name cod-test-minio -p 59000:9000 -p 59001:9001 \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"

export R2_TEST_ENDPOINT=http://localhost:59000
```

The image pipeline unit/integration tests (`backend/tests/domains/images/`,
`backend/tests/services/test_banner_upload_service.py`) use an in-process
`FakeR2Client`/`FakeUnavailableR2Client` (`tests/storage/fakes.py`) and need
no external service; the real MinIO endpoint is only required for
`test_r2_client.py` itself.

### Frontend

```bash
# Linting
pnpm --prefix frontend run lint

# Type checking
pnpm --prefix frontend run typecheck

# Tests (single-run, not watch)
pnpm --prefix frontend run test -- --run

# Production build
pnpm --prefix frontend run build
```

## Integration Tests

End-to-end integration tests must prove the critical path:

1. Publish active product
2. Open `/p/{slug}`
3. Click CTA
4. Submit COD form
5. Apply fraud rules
6. Find order and flags in admin

Also test:
- Non-fraud path (order goes to `pending`)
- Duplicate path (duplicate detected → `flagged_fraud`)
- Blacklist path (phone/IP blacklisted → `flagged_fraud`)
- Rate-limit path (exceeded threshold → `flagged_fraud`)
- GeoIP `flag` and `block` paths (both persist a reviewable `flagged_fraud`
  order; `block` is never a silent drop)
- Draft/paused/retired/unknown denial (one identical 404)
- Admin review: the order and its flags are readable through
  `/api/admin/orders`, and anonymous callers get 401

These live in `backend/tests/e2e/test_cod_flow.py`.

## Pre-Merge Checklist

Before merging:

1. Run targeted tests for changed behavior
2. Run complete relevant backend/frontend suite
3. Run static checks (lint, format, typecheck)
4. Run production frontend build
5. For migration changes:
   - Test clean-database upgrade
   - Test upgrade from previous release schema
6. For infrastructure changes:
   - Test deployment configuration (no long-running processes in automated sessions)

## CI Requirements

Automated CI must run:
- All backend validation commands
- All frontend validation commands
- Integration test suite
- Migration validation (if schema changed)

If a command cannot run because scaffolding or a dependency is not present, state that explicitly. Do not fabricate successful validation.

## Test Data

Use obviously synthetic test data. Never include:
- Real secrets
- Real customer data
- Full sensitive records
- Production credentials
- Actual addresses or phone numbers (except documented test examples)

Colombian phone test examples (for documentation):
- `+573001234567` (normalized form)
- `57 300 123 4567` (with spaces)
- `300-123-4567` (without country code)
- `(300) 123-4567` (with parentheses)

All must normalize to `+573001234567`.

## Property Generator Bounds

Keep property generators bounded so the suite remains deterministic for CI. Report seeds for failures rather than hiding flaky behavior.

```python
# ✓ Good — bounded, deterministic
@given(banners=st.lists(st.integers(), min_size=1, max_size=15))
def test_banner_ordering(banners):
    ...

# ✗ Bad — unbounded, potential for flaky failures
@given(banners=st.lists(st.integers()))  # can generate huge lists
def test_banner_ordering(banners):
    ...
```
