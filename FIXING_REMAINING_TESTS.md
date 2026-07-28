# Guide to Fixing Remaining Test Failures

## 🎯 Quick Reference

| Issue | Tests Affected | Severity | Fix Time |
|-------|---|----------|----------|
| Phone Normalization | 5 tests | High | 15 min |
| Database Setup | 77 tests (skipped) | High | 30 min |
| Redis Setup | 12 tests | Medium | 20 min |
| CSV Export Encoding | 1 test | Low | 10 min |
| **Total** | **30 failures** | - | ~1.5 hrs |

---

## 1. 🔴 Phone Normalization Tests (5 failures)

### Problem
```
tests/domains/orders/test_phone_normalization.py
- test_normalization_is_idempotent
- test_equivalent_representations_produce_same_key
- test_key_is_national_number_without_plus57
- test_key_without_country_code
- test_normalization_of_normalized_input
```

### Root Cause
Missing phonenumbers library or implementation in phone validation

### Solution

1. **Install phonenumbers library** (if not already installed):
```bash
pip install phonenumbers==8.13.0
```

2. **Check implementation** in:
```
backend/app/domains/orders/
```

3. **Verify the phone normalization function handles**:
   - Colombian phone format validation
   - Stripping country code (+57)
   - Normalizing different number formats to standard key
   - Idempotent normalization (normalize(normalize(x)) == normalize(x))

### Test to Run
```bash
python -m pytest tests/domains/orders/test_phone_normalization.py -v
```

---

## 2. 🔵 Database Setup (77 skipped tests)

### Problem
Tests are skipped because `DATABASE_URL` environment variable is not set

### Solution

#### Option A: Local PostgreSQL (Recommended for Development)

1. **Install PostgreSQL** (if needed):
   - Download from https://www.postgresql.org/download/
   - Or use `choco install postgresql` on Windows

2. **Create test database**:
```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE cod_platform_dev;
CREATE DATABASE cod_platform_test;
```

3. **Set environment variable**:

**Windows PowerShell**:
```powershell
$env:DATABASE_URL = "postgresql://postgres:password@localhost:5432/cod_platform_test"
```

**Or create `.env` file** in backend directory:
```bash
DATABASE_URL="postgresql://postgres:password@localhost:5432/cod_platform_test"
```

Then load it:
```bash
# Add to backend/.env file
DATABASE_URL=postgresql://postgres:password@localhost:5432/cod_platform_test
```

4. **Run migrations**:
```bash
prisma migrate deploy
```

5. **Verify connection**:
```bash
python -c "import os; print(os.environ.get('DATABASE_URL'))"
```

#### Option B: Neon Cloud PostgreSQL

1. **Create free account** at https://console.neon.tech/
2. **Create project** and copy connection string
3. **Set environment variable**:
```powershell
$env:DATABASE_URL = "postgresql://user:password@ep-XXXX.neon.tech/dbname"
```

### Tests That Will Unlock
```bash
python -m pytest tests/db -v
python -m pytest tests/e2e -v
python -m pytest tests -v --co -q | grep "requires_database"
```

---

## 3. 🟡 Redis Setup (12 fraud detection test failures)

### Problem
Fraud tests require Redis for rate limiting functionality

### Solution

#### Option A: Upstash Redis (Cloud - Recommended)

1. **Create free account** at https://upstash.com/
2. **Create Redis database**
3. **Copy credentials**:
   - REST URL
   - REST Token

4. **Set environment variables**:

**Windows PowerShell**:
```powershell
$env:UPSTASH_REDIS_REST_URL = "https://xxx.upstash.io"
$env:UPSTASH_REDIS_REST_TOKEN = "xxx"
```

**Or `.env` file**:
```
UPSTASH_REDIS_REST_URL=https://xxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=xxx
```

#### Option B: Local Redis

1. **Install Redis**:
   ```bash
   # Windows: Use Windows Subsystem for Linux (WSL)
   # Or download from https://github.com/microsoftarchive/redis/releases
   ```

2. **Start Redis server**:
   ```bash
   redis-server
   ```

3. **Install Redis client for Python** (should be installed already):
   ```bash
   pip install upstash-redis
   ```

### Tests That Will Unlock
```bash
python -m pytest tests/domains/fraud -v
```

**Specific tests**:
- `test_duplicate_detection_no_false_positives`
- `test_duplicate_detection_with_matching_fields`
- `test_rate_limit_trigger_when_count_exceeds_limit`
- `test_geoip_flag_with_country_match`
- etc.

---

## 4. 🟠 CSV Export Test (1 failure)

### Problem
```
tests/services/test_csv_export_service.py::TestCsvExportSafety::test_customer_strings_remain_readable_after_export
```

### Investigation Steps

1. **Run test with full traceback**:
```bash
python -m pytest tests/services/test_csv_export_service.py::TestCsvExportSafety::test_customer_strings_remain_readable_after_export -vv --tb=long
```

2. **Check the test file**:
```
backend/app/services/csv_export_service.py
backend/tests/services/test_csv_export_service.py
```

3. **Likely fixes**:
   - Add UTF-8 encoding to CSV writer
   - Handle special characters (Colombian diacritics, etc.)
   - Ensure proper escaping for comma-separated values

### Example Fix
```python
# In csv_export_service.py
import csv
from io import StringIO

def export_orders_to_csv(orders):
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=['name', 'phone', 'address', ...])
    writer.writeheader()
    
    for order in orders:
        writer.writerow({
            'name': order.customer_name,
            'phone': order.customer_phone,
            'address': order.customer_address,
            # ... other fields
        })
    
    return output.getvalue().encode('utf-8')
```

---

## 5. 🟣 E2E COD Flow Tests (3 failures)

### Problem
```
tests/e2e/test_cod_flow.py
- test_e2e_cod_flow_clean_order
- test_e2e_cod_flow_duplicate_detection
- test_e2e_cod_flow_not_found_denial
```

**Note**: These will fail until DATABASE_URL + full environment is set up (see section 2)

### What These Test
- Complete COD order submission flow
- Fraud detection in real scenarios
- Proper error handling

### To Run
```bash
# After setting DATABASE_URL and running migrations
python -m pytest tests/e2e -v
```

---

## 📋 Full Test Recovery Checklist

```bash
# Step 1: Phone validation
☐ pip install phonenumbers
☐ python -m pytest tests/domains/orders/test_phone_normalization.py -v

# Step 2: Database
☐ Create PostgreSQL database
☐ Set DATABASE_URL environment variable
☐ prisma migrate deploy
☐ python -m pytest tests/db -v
☐ python -m pytest tests/e2e -v

# Step 3: Redis
☐ Create Upstash Redis account (or start local Redis)
☐ Set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN
☐ python -m pytest tests/domains/fraud -v

# Step 4: CSV Export
☐ python -m pytest tests/services/test_csv_export_service.py -v
☐ Fix encoding if needed

# Step 5: Full suite validation
☐ python -m pytest tests -v
```

---

## 🚀 Running Full Test Suite

Once all environment variables are set:

```bash
# Verbose output
python -m pytest tests -v

# With coverage report
python -m pytest tests --cov=app --cov-report=html

# Quick summary
python -m pytest tests --tb=short -q

# Only show failures
python -m pytest tests -v --lf

# Run specific test category
python -m pytest tests/domains -v
python -m pytest tests/services -v
python -m pytest tests/e2e -v
```

---

## 📊 Expected Results After Fixes

```
Target: 226+ passed (from current 196)
- Core tests: ✅ 38/38
- Product tests: ✅ 33/33
- Landing tests: ✅ (depends on your implementation)
- Order tests: ❌ 5 (after phone normalization fix)
- Fraud tests: ❌ 12 (after Redis setup)
- DB tests: ❌ 77 (after Database setup)
- E2E tests: ❌ 3 (after Database + Redis setup)
- CSV export: ❌ 1 (after encoding fix)
```

---

## 🆘 Troubleshooting

### "DATABASE_URL not set"
```bash
# Windows PowerShell
$env:DATABASE_URL = "postgresql://..."
echo $env:DATABASE_URL  # Verify it's set

# Or edit backend/.env
DATABASE_URL=postgresql://...
```

### "ConnectionError: Redis connection failed"
```bash
# Verify Redis is running
# Check UPSTASH_REDIS_REST_URL is correct
# Test connection:
python -c "from upstash_redis import Redis; r = Redis.from_env(); print(r.ping())"
```

### "Prisma client not generated"
```bash
prisma generate
```

### "ModuleNotFoundError: No module named 'phonenumbers'"
```bash
pip install phonenumbers==8.13.0
```

---

## 📖 Reference Files

- Test config: `backend/pytest.ini`
- Test fixtures: `backend/tests/conftest.py`
- Requirements: `backend/requirements.txt` and `backend/requirements-dev.txt`
- Database schema: `prisma/schema.prisma`
- Environment template: (Create `backend/.env`)

---

## ✅ Success Indicators

- [ ] All core tests pass: `python -m pytest tests/core -v`
- [ ] Product tests pass: `python -m pytest tests/domains/products -v`
- [ ] No internal pytest errors
- [ ] Test summary shows "passed" instead of "FAILED"

Once all external services are configured, expect **226+ tests to pass** ✅
