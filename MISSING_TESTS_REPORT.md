# ⚠️ MISSING TEST COVERAGE REPORT

**Status**: 🔴 INCOMPLETE - Required tests not implemented  
**Date**: July 24, 2026  
**Severity**: HIGH - Blocks pre-merge checklist

---

## Summary

According to `docs/testing.md`, **9 required property-based tests** are specified. Current status:

| # | Test Category | Location | Status | Required |
|----|---------------|----------|--------|----------|
| 1 | Banner reordering | `tests/domains/landings/test_banner_ordering.py` | ✅ EXISTS | YES |
| 2 | CTA placement | `tests/domains/landings/test_cta_placement.py` | ✅ EXISTS | YES |
| 3 | **Phone normalization** | `tests/domains/orders/` | 🔴 **MISSING** | **YES** |
| 4 | **Order status transitions** | `tests/domains/orders/` | 🔴 **MISSING** | **YES** |
| 5 | **Fraud classification** | `tests/domains/fraud/` | 🔴 **MISSING** | **YES** |
| 6 | **Duplicate detection** | `tests/domains/fraud/` | 🔴 **MISSING** | **YES** |
| 7 | **Rate limiting** | `tests/redis/test_rate_limit.py` | ⚠️ Placeholder | **YES** |
| 8 | **Image generation** | `tests/domains/images/` | ⚠️ Partial | **YES** |
| 9 | **CSV safety** | `tests/services/` | 🔴 **MISSING** | **YES** |

**Result**: 2 complete ✅ | 3 partial ⚠️ | 4 missing 🔴 | **34% coverage**

---

## Missing Test Suites

### 🔴 1. Orders Domain Tests (CRITICAL)

**Location**: `backend/tests/domains/orders/` (DOES NOT EXIST)

**Required Tests**:

#### A. Phone Normalization (Property Test)
```python
# tests/domains/orders/test_phone_normalization.py

@given(
    phone=st.one_of(
        st.just("+573001234567"),           # Already normalized
        st.just("57 300 123 4567"),         # With spaces
        st.just("300-123-4567"),            # Without country code
        st.just("(300) 123-4567"),          # With parentheses
    )
)
def test_normalization_is_idempotent(phone: str) -> None:
    """For any accepted phone representation, normalize(normalize(x)) == normalize(x)."""
    normalized_once = normalize_colombian_phone(phone)
    normalized_twice = normalize_colombian_phone(normalized_once)
    assert normalized_once == normalized_twice

@given(
    phone1=st.just("+573001234567"),
    phone2=st.just("57 300 123 4567"),
    phone3=st.just("3001234567"),
)
def test_equivalent_representations_produce_same_key(phone1: str, phone2: str, phone3: str) -> None:
    """Equivalent phone representations produce identical matching keys."""
    key1 = normalize_colombian_phone_key(phone1)
    key2 = normalize_colombian_phone_key(phone2)
    key3 = normalize_colombian_phone_key(phone3)
    assert key1 == key2 == key3
```

**What it tests**:
- ✓ Idempotency of normalization
- ✓ Equivalent formats produce same key
- ✓ Boundaries: +57 prefix, spaces, hyphens, country codes

---

#### B. Order Status Transitions (Property Test)
```python
# tests/domains/orders/test_status_transitions.py

@given(
    current_status=st.sampled_from(["pending", "confirmed", "shipped", "delivered", "cancelled", "flagged_fraud"]),
    target_status=st.sampled_from(["pending", "confirmed", "shipped", "delivered", "cancelled", "flagged_fraud"]),
)
def test_only_documented_transitions_succeed(current_status: str, target_status: str) -> None:
    """For any order state and requested transition, only the documented transition 
    graph can change persisted status."""
    valid_transitions = {
        "pending": {"confirmed", "cancelled"},
        "confirmed": {"shipped", "cancelled"},
        "shipped": {"delivered", "cancelled"},
        "flagged_fraud": {"pending", "cancelled"},
        "delivered": set(),
        "cancelled": set(),
    }
    
    if target_status in valid_transitions.get(current_status, set()):
        # Should succeed
        result = validate_status(current_status, target_status)
        assert result is None  # No exception raised
    else:
        # Should fail
        with pytest.raises(InvalidOrderStatusTransition):
            validate_status(current_status, target_status)
```

**What it tests**:
- ✓ Only legal transitions allowed
- ✓ Illegal transitions raise InvalidOrderStatusTransition
- ✓ Transition graph is enforced

---

### 🔴 2. Fraud Domain Tests (CRITICAL)

**Location**: `backend/tests/domains/fraud/` (DOES NOT EXIST)

**Required Tests**:

#### A. Fraud Classification (Property Test)
```python
# tests/domains/fraud/test_fraud_classification.py

@given(
    has_duplicate=st.booleans(),
    has_blacklist=st.booleans(),
    has_rate_limit_phone=st.booleans(),
    has_rate_limit_ip=st.booleans(),
    has_geoip=st.booleans(),
)
def test_classification_is_pending_iff_no_rules_trigger(
    has_duplicate: bool,
    has_blacklist: bool,
    has_rate_limit_phone: bool,
    has_rate_limit_ip: bool,
    has_geoip: bool,
) -> None:
    """For any set of fraud rule outcomes, classification is `pending` exactly when 
    no rule triggers; otherwise classification is `flagged_fraud` and all triggered 
    rule identities are preserved."""
    
    flags = []
    if has_duplicate:
        flags.append(FraudFlag(..., flag_type=FLAG_TYPE_DUPLICATE, ...))
    if has_blacklist:
        flags.append(FraudFlag(..., flag_type=FLAG_TYPE_BLACKLIST, ...))
    # ... etc for other rules
    
    aggregated = aggregate_flags(flags)
    
    if not flags:
        assert len(aggregated) == 0  # pending
    else:
        assert len(aggregated) > 0  # flagged_fraud
        assert all(f.flag_type in triggered_types for f in aggregated)
```

**What it tests**:
- ✓ Classification is `pending` iff no flags
- ✓ Classification is `flagged_fraud` iff flags exist
- ✓ All flag types are preserved in output

---

#### B. Duplicate Detection (Property Test)
```python
# tests/domains/fraud/test_duplicate_detection.py

@given(
    window_hours=st.integers(min_value=1, max_value=72),
    match_field_count=st.integers(min_value=1, max_value=2),  # phone, ip
    orders_in_window=st.integers(min_value=0, max_value=5),
)
def test_duplicate_window_boundary_behavior(
    window_hours: int,
    match_field_count: int,
    orders_in_window: int,
) -> None:
    """For any duplicate-window boundary, only records inside the configured 
    interval with all configured match fields equal trigger duplicate detection."""
    
    config = FraudConfig(
        duplicate_window_hours=window_hours,
        duplicate_match_fields={"phone", "ip"}[:match_field_count],
        ...
    )
    
    # Create test data with orders at boundary
    now = datetime.utcnow()
    inside_window = []
    outside_window = []
    
    # ... create orders inside/outside window
    
    flags = check_duplicate(db, phone_key="...", ip="...", config=config)
    
    if all_fields_match and order_is_inside_window:
        assert len(flags) > 0
    else:
        assert len(flags) == 0
```

**What it tests**:
- ✓ Duplicate detected only in configured window
- ✓ All match fields must be equal
- ✓ Boundary cases handled correctly

---

#### C. Rate Limiting (Property Test)
```python
# tests/domains/fraud/test_rate_limit.py  

@given(
    attempts=st.integers(min_value=0, max_value=20),
    window_minutes=st.integers(min_value=1, max_value=120),
    max_attempts=st.integers(min_value=1, max_value=10),
    attempt_timing=st.lists(st.integers(min_value=0, max_value=1000)),
)
def test_rate_limit_rolling_window_accuracy(
    attempts: int,
    window_minutes: int,
    max_attempts: int,
    attempt_timing: list[int],
) -> None:
    """For any attempt stream, rolling-window counts do not include attempts 
    outside the configured interval and trigger at the documented threshold."""
    
    config = FraudConfig(
        rate_limit_window_minutes=window_minutes,
        rate_limit_max=max_attempts,
    )
    
    # Simulate attempts over time
    now = datetime.utcnow()
    results = []
    for i, offset_ms in enumerate(attempt_timing):
        timestamp = now - timedelta(milliseconds=offset_ms)
        result = await check_rate_limit(redis, key, max_attempts, window_seconds*60)
        results.append(result)
        await redis.increment(key)
    
    # Verify only in-window attempts counted
    for i, result in enumerate(results):
        expected_count = sum(1 for j in range(i+1) 
                             if attempt_timing[j] <= window_minutes*60*1000)
        assert result.count == expected_count or result.count > max_attempts
        if result.count > max_attempts:
            assert result.triggered
```

**What it tests**:
- ✓ Only in-window attempts counted
- ✓ Threshold triggers correctly
- ✓ Rolling window excludes old attempts

---

### 🔴 3. CSV Export Safety Test (CRITICAL)

**Location**: `backend/tests/services/test_csv_export_service.py` (File exists but tests missing)

**Required Property Test**:

```python
# Add to test_csv_export_service.py

@given(
    customer_string=st.text(
        alphabet=st.characters(
            blacklist_categories=("Cc",),  # No control chars
        ),
        min_size=0,
        max_size=500,
    )
)
def test_csv_export_prevents_formula_injection(customer_string: str) -> None:
    """For any exported customer string, CSV encoding round-trips as data 
    and cannot become an executable spreadsheet formula."""
    
    orders = [{
        "customer_name": customer_string,
        "phone_e164": "+573001234567",
        # ... other fields
    }]
    
    service = CsvExportService()
    csv_content = service.export_orders(orders=orders)
    
    # Parse CSV to verify it round-trips correctly
    lines = csv_content.split('\n')
    data_rows = [line for line in lines if line.strip()]
    
    if data_rows:
        # Verify formula control characters are neutralized
        for row in data_rows[1:]:  # Skip header
            if customer_string:
                # Should not start with formula characters
                assert not any(row.startswith(c) for c in ["=", "+", "-", "@", "\t"])
        
        # Verify round-trip
        import csv
        import io
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)
        # ... assert original value is recoverable (possibly with escape prefix)
```

**What it tests**:
- ✓ Formula control characters neutralized
- ✓ String remains readable after encoding
- ✓ Round-trip data integrity

---

### ⚠️ 4. Image Generation (Partial Coverage)

**Location**: `backend/tests/domains/images/`

**What exists**: Some basic tests in:
- test_validation.py
- test_variants.py
- test_exif.py
- test_opaque_key.py

**What's missing**: Comprehensive property test for aspect ratio preservation:

```python
# Add to test_variants.py

@given(
    source_width=st.integers(min_value=480, max_value=8000),
    source_height=st.integers(min_value=1, max_value=8000),
)
def test_generated_variants_preserve_aspect_ratio(
    source_width: int,
    source_height: int,
) -> None:
    """For any supported source dimensions, generated widths are from the 
    configured set, are no larger than the source, and preserve aspect 
    ratio within encoding tolerance."""
    
    source_aspect = source_width / source_height
    
    for variant in generate_variants(source_width, source_height):
        # Check width is from configured set
        assert variant.width in {480, 768, 1200, 1600}
        # Check width doesn't exceed source
        assert variant.width <= source_width
        # Check aspect ratio preserved within tolerance
        variant_aspect = variant.width / variant.height
        assert abs(variant_aspect - source_aspect) < 0.01  # 1% tolerance
```

---

### ⚠️ 5. Rate Limit Tests (Placeholder)

**Location**: `backend/tests/redis/test_rate_limit.py`

**Status**: File exists but appears to be a skeleton. Need to verify coverage of:
- ✓ Atomic increment with TTL
- ✓ Rolling window boundary conditions
- ✓ Concurrent increment operations
- ✓ Fallback when Redis unavailable

---

## What's Blocking Pre-Merge

From `docs/testing.md` Pre-Merge Checklist:

```
Before merging:
1. ❌ Run targeted tests for changed behavior
2. ❌ Run complete relevant backend/frontend suite
3. ✅ Run static checks (lint, format, typecheck)
4. ✅ Run production frontend build
5. ❌ For migration changes: test upgrade paths
6. ❌ For infrastructure changes: test deployment
```

**Cannot proceed without**:
- [ ] All 9 required property tests implemented
- [ ] Orders domain test suite
- [ ] Fraud domain test suite
- [ ] CSV export safety test
- [ ] Full pytest run passing

---

## Recommended Action Plan

### Phase 1: Create Missing Test Files (Priority: HIGH)
```bash
# Create test directories
mkdir -p backend/tests/domains/orders
mkdir -p backend/tests/domains/fraud

# Create test files
touch backend/tests/domains/orders/test_phone_normalization.py
touch backend/tests/domains/orders/test_status_transitions.py
touch backend/tests/domains/fraud/test_fraud_classification.py
touch backend/tests/domains/fraud/test_duplicate_detection.py
touch backend/tests/domains/fraud/test_rate_limit.py
touch backend/tests/services/test_csv_export_service_safety.py
```

### Phase 2: Implement Property Tests (Priority: CRITICAL)
Each test file should include:
- Unit tests for validation
- Property-based tests using Hypothesis
- Boundary/edge case coverage
- Counterexample regression tests

### Phase 3: Run Full Test Suite
```bash
python -m pytest backend/tests -v --hypothesis-seed=0
```

---

## Files That Need Tests

### Orders Domain
- [x] `backend/app/domains/orders/normalization.py` - **NEEDS** test_phone_normalization.py
- [x] `backend/app/domains/orders/normalization.py` - **NEEDS** test_status_transitions.py

### Fraud Domain
- [x] `backend/app/domains/fraud/checks.py` - **NEEDS** test_fraud_classification.py
- [x] `backend/app/domains/fraud/checks.py` - **NEEDS** test_duplicate_detection.py
- [x] `backend/app/domains/fraud/checks.py` - **NEEDS** test_rate_limit.py

### Services
- [x] `backend/app/services/csv_export_service.py` - **NEEDS** CSV safety property test

---

## Validation Commands

After implementing tests, run:

```bash
# Backend tests
python -m pytest backend/tests -v

# With coverage
python -m pytest backend/tests --cov=backend/app --cov-report=term-missing

# Property-based tests with seed for reproducibility
python -m pytest backend/tests --hypothesis-seed=12345

# Specific test file
python -m pytest backend/tests/domains/orders/test_phone_normalization.py -v
```

---

## Current Test Coverage

### What Exists ✅
- Banner ordering (property)
- CTA placement (property)
- Product lifecycle
- Landing publication
- Banner upload service
- Auth service
- Health check
- Schema constraints
- Repository tests

### What's Missing 🔴
- Phone normalization (property)
- Order status transitions (property)
- Fraud classification (property)
- Duplicate detection (property)
- Rate limiting (property)
- CSV safety (property)
- Integration tests for COD flow

---

## Conclusion

**Status**: Tests are **incomplete**. While code compiles and runs, it lacks the required property-based test coverage specified in `docs/testing.md`.

**Next Step**: Implement the 4 missing test suites (Orders, Fraud×3, CSV) before marking as production-ready.

**Estimated Effort**: 8-12 hours for complete implementation and validation.
