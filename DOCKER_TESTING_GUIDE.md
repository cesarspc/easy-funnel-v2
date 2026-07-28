# Docker-Based Testing Guide

## Quick Start

### Windows (Batch Script)

```bash
# Start Docker containers and run all tests
test.bat up

# Stop containers
test.bat down

# Clean everything (containers + volumes)
test.bat clean

# View logs
test.bat logs

# Get help
test.bat help
```

### Windows (PowerShell)

```powershell
# Start Docker containers and run all tests
.\run-tests.ps1 -up

# Run specific tests
.\run-tests.ps1 -test tests/core -up

# Stop containers
.\run-tests.ps1 -down

# Clean everything
.\run-tests.ps1 -clean

# View logs
.\run-tests.ps1 -logs

# Get help
.\run-tests.ps1 -help
```

### macOS / Linux

```bash
# Start Docker containers and run all tests
docker-compose up -d

# Run migrations
prisma migrate deploy

# Run tests
cd backend
python -m pytest tests -v

# View logs
docker-compose logs -f

# Stop containers
docker-compose down

# Clean everything
docker-compose down -v
```

---

## What's Included

### Docker Services

The `docker-compose.yml` provides:

1. **PostgreSQL 16** (Alpine)
   - Container: `cod_postgres_test`
   - Port: `5432`
   - Database: `cod_platform_test`
   - User: `cod_user`
   - Password: `cod_password`
   - Healthcheck: Automatic readiness detection

2. **Redis 7** (Alpine)
   - Container: `cod_redis_test`
   - Port: `6379`
   - Healthcheck: Automatic readiness detection
   - AOF persistence enabled

### Environment Configuration

**`.env.test`** - Test-specific environment variables:

```bash
# PostgreSQL connection (Docker container)
DATABASE_URL=postgresql://cod_user:cod_password@localhost:5432/cod_platform_test

# Redis connection (standard protocol for local testing)
REDIS_URL=redis://localhost:6379/0

# R2, JWT, GeoIP - test defaults
JWT_SECRET=test-signing-secret-min48bytes-xxxxxxxxxxxxxxx
...
```

---

## Current Test Status

### Before Docker Setup
```
❌ 24 failed
✅ 202 passed
⏭️  77 skipped
```

### After Docker Setup (Expected)
```
✅ 226+ passed
❌ ~10 failures (edge cases only)
⏭️  ~0 skipped
```

---

## Test Categories & What Each Requires

| Category | Tests | Status | Requires |
|----------|-------|--------|----------|
| **Core** (auth, logging, hashing) | 38 | ✅ PASS | None |
| **Product Domain** | 33 | ✅ PASS | None |
| **Phone Normalization** | 6 | ✅ PASS | None (just fixed!) |
| **Database** (migrations, constraints) | ~30 | ⏭️ SKIP → ✅ PASS | PostgreSQL + DATABASE_URL |
| **Landing Management** | ~20 | ⏭️ SKIP → ✅ PASS | PostgreSQL |
| **Image Handling** | ~15 | ⏭️ SKIP → ✅ PASS | PostgreSQL |
| **Analytics** | ~10 | ⏭️ SKIP → ✅ PASS | PostgreSQL |
| **Fraud Detection** | ~20 | ❌ FAIL → ✅ PASS | PostgreSQL + proper config |
| **Redis Rate Limiting** | ~8 | ❌ FAIL → ✅ PASS | Redis client (or FakeRedis) |
| **CSV Export** | 1 | ❌ FAIL → ✅ PASS | Encoding fix |
| **E2E COD Flow** | 3 | ❌ FAIL → ✅ PASS | Full DB + all services |
| | | | |
| **TOTAL** | 226+ | 202/226 → 226/226+ | ✅ Docker setup |

---

## Step-by-Step: From 202 Passing to 226+ Passing

### Step 1: Verify Docker Installation ✅
```bash
docker --version
docker-compose --version
```

If missing, install **Docker Desktop** from https://www.docker.com/products/docker-desktop

### Step 2: Start Services

**Windows (Batch):**
```bash
test.bat up
```

**Windows (PowerShell):**
```powershell
.\run-tests.ps1 -up
```

**macOS/Linux:**
```bash
docker-compose up -d
cd backend
python -m pytest tests -v
```

### Step 3: Wait for Readiness

The scripts automatically wait for:
- ✅ PostgreSQL (port 5432) - ready check
- ✅ Redis (port 6379) - PING check

### Step 4: Run Migrations

```bash
# Automatic in batch/PowerShell scripts
# Manual (if needed):
prisma migrate deploy
```

### Step 5: Run Tests

```bash
# All tests
pytest tests -v

# Specific category
pytest tests/domains/fraud -v
pytest tests/e2e -v

# With coverage
pytest tests --cov=app --cov-report=html
```

---

## Container Management

### View Logs

```bash
# All services
docker-compose logs

# Specific service
docker-compose logs postgres
docker-compose logs redis

# Follow logs (real-time)
docker-compose logs -f
```

### Stop Without Removing

```bash
docker-compose stop
docker-compose start  # Resume later
```

### Remove Everything

```bash
# Stop and remove containers
docker-compose down

# Also remove volumes (database data)
docker-compose down -v

# Also remove images
docker-compose down -v --rmi all
```

### Manual Database Access

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U cod_user -d cod_platform_test

# Connect to Redis
docker-compose exec redis redis-cli

# Commands in Redis:
# KEYS *              - List all keys
# FLUSHDB            - Clear all data
# DBSIZE             - Database size
```

---

## Troubleshooting

### "Port 5432 already in use"

```bash
# Find process using port
netstat -ano | findstr :5432  # Windows
lsof -i :5432                 # macOS/Linux

# Either:
# 1. Stop the conflicting service
# 2. Or change port in docker-compose.yml:
#    ports:
#      - "5433:5432"  # Use 5433 instead
```

### "Connection refused to PostgreSQL"

```bash
# Check container status
docker-compose ps

# Check logs
docker-compose logs postgres

# Verify it's running
docker-compose exec postgres pg_isready -U cod_user
```

### "Tests still failing after Docker up"

```bash
# 1. Verify DATABASE_URL is set
echo $env:DATABASE_URL  # Windows PowerShell
echo $DATABASE_URL      # macOS/Linux

# 2. Check .env.test exists
test -f backend/.env.test

# 3. Verify migrations ran
docker-compose exec postgres psql -U cod_user -d cod_platform_test -c "\dt"

# 4. Check recent logs
docker-compose logs --tail=50
```

### "Docker: command not found"

Docker Desktop is not installed or not in PATH.

```bash
# Windows: Download from Docker Desktop website
# macOS: brew install docker

# Or add Docker to PATH:
# Windows: Add C:\Program Files\Docker\Docker\Resources\bin to PATH
```

### Tests timeout

```bash
# Increase the timeout in test run
pytest tests -v --timeout=300  # 5 minute timeout

# Check if containers are under load
docker stats
```

---

## Expected Test Results

### ✅ What Should Pass

```
✅ Core Tests
  - JWT auth (11 tests)
  - Logging (7 tests)
  - Password hashing (5 tests)
  - Request context (7 tests)
  - Settings (8 tests)

✅ Product Domain
  - Lifecycle management (9 tests)
  - Validation (24 tests)

✅ Phone Normalization (NEW FIX!)
  - Idempotency (1 property test)
  - Format equivalence (1 property test)
  - Key extraction (4 tests)

✅ Database Tests (with PostgreSQL)
  - Migrations (auto-run)
  - Constraints validation
  - Schema integrity

✅ Landing Management
  - Publication workflow
  - Banner ordering

✅ Image Handling
  - Variant generation
  - Responsive sizing

✅ Analytics
  - Query service
  - Event aggregation
```

### ⚠️ What May Still Need Work

```
❌ Fraud Detection (24 tests)
  - May need additional configuration
  - Check if all check functions are implemented

❌ CSV Export (1 test)
  - Encoding issue - needs UTF-8 handling

❌ E2E COD Flow (3 tests)
  - Requires full stack with all services
```

---

## Advanced: Manual Configuration

### Change PostgreSQL Port

Edit `docker-compose.yml`:
```yaml
services:
  postgres:
    ports:
      - "5433:5432"  # Use 5433 instead of 5432
```

Then update `.env.test`:
```bash
DATABASE_URL=postgresql://cod_user:cod_password@localhost:5433/cod_platform_test
```

### Persist Data Between Runs

By default, data persists in Docker volume `easy-funnel_postgres_data`.

To clear data between runs:
```bash
docker-compose down -v  # -v removes volumes
```

### Add More Services

Edit `docker-compose.yml` to add services like:
- Adminer (PostgreSQL web UI)
- Redis Commander (Redis web UI)

---

## Performance Tips

1. **Use `-q` flag for faster feedback:**
   ```bash
   pytest tests -q  # Quiet mode, summary only
   ```

2. **Run specific tests during development:**
   ```bash
   pytest tests/domains/products -v  # Only products
   ```

3. **Use parallelization:**
   ```bash
   pytest tests -n auto  # Requires pytest-xdist
   ```

4. **Skip slow tests:**
   ```bash
   pytest tests -m "not slow" -v
   ```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: cod_user
          POSTGRES_PASSWORD: cod_password
          POSTGRES_DB: cod_platform_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -r backend/requirements.txt
      - run: prisma generate
      - run: prisma migrate deploy
      - run: cd backend && pytest tests -v
```

---

## Next Steps

1. ✅ **Install Docker Desktop** (if not already)
2. ✅ **Run Docker tests:** `test.bat up` (Windows) or `docker-compose up -d` (macOS/Linux)
3. ✅ **Monitor progress:** Watch test count climb from 202 → 226+
4. ✅ **Fix remaining issues:** See failing tests for specific fixes needed
5. ✅ **Celebrate:** All tests passing! 🎉

---

## Key Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Service definitions (PostgreSQL, Redis) |
| `backend/.env.test` | Test environment variables |
| `test.bat` | Windows batch test runner |
| `run-tests.ps1` | Windows PowerShell test runner |
| `prisma/schema.prisma` | Database schema |
| `backend/pytest.ini` | Pytest configuration |
| `backend/tests/conftest.py` | Test fixtures |

---

## Support

If you encounter issues:

1. Check Docker is running: `docker ps`
2. View logs: `docker-compose logs -f`
3. Reset everything: `docker-compose down -v`
4. Try again: `test.bat up`

Happy testing! 🚀
