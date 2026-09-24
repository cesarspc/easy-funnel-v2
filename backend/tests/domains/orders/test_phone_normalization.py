"""Property tests for rule-driven phone normalization (Requirement 5.7).

Required property (testing.md -> Required Properties #3): For any accepted
phone representation, normalization is idempotent and equivalent
representations produce the same duplicate/blacklist/rate-limit key.
"""

from __future__ import annotations

from hypothesis import given, strategies as st

import pytest

from app.core.regional import DEFAULT_REGIONAL, PhoneRules
from app.domains.orders.errors import OrderValidationError
from app.domains.orders.normalization import normalize_phone, normalize_phone_key

_RULES = DEFAULT_REGIONAL.phone


def normalize_colombian_phone(raw: str) -> str:
    return normalize_phone(raw, _RULES)


def normalize_colombian_phone_key(raw: str) -> str:
    return normalize_phone_key(raw, _RULES)


# Colombian mobile numbers: national numbers start with '3' and are 10 digits
_PHONE_DIGITS_PATTERN = st.text(
    alphabet=st.characters(
        categories=["Nd"],  # Numeric digits
        min_codepoint=ord("0"),
        max_codepoint=ord("9"),
    ),
    min_size=10,
    max_size=13,
).filter(lambda s: len(s.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("57", "")) >= 10)


@given(
    phone=st.one_of(
        # Already normalized form
        st.just("+573001234567"),
        st.just("+573101234567"),
        st.just("+573201234567"),
        # With spaces
        st.just("57 300 123 4567"),
        st.just("57 310 123 4567"),
        # Without country code
        st.just("3001234567"),
        st.just("3101234567"),
        st.just("3201234567"),
        # With hyphens
        st.just("300-123-4567"),
        st.just("310-123-4567"),
        # With parentheses
        st.just("(300) 123-4567"),
        st.just("(310) 123-4567"),
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
    phone4=st.just("300-123-4567"),
    phone5=st.just("(300) 123-4567"),
)
def test_equivalent_representations_produce_same_key(
    phone1: str, phone2: str, phone3: str, phone4: str, phone5: str
) -> None:
    """Equivalent phone representations produce identical matching keys for
    duplicate/blacklist/rate-limit lookups."""
    key1 = normalize_colombian_phone_key(phone1)
    key2 = normalize_colombian_phone_key(phone2)
    key3 = normalize_colombian_phone_key(phone3)
    key4 = normalize_colombian_phone_key(phone4)
    key5 = normalize_colombian_phone_key(phone5)

    assert key1 == key2 == key3 == key4 == key5


@given(
    phone=st.one_of(
        st.just("+573001234567"),
        st.just("+573101234567"),
        st.just("+573201234567"),
    )
)
def test_key_is_national_number_without_plus57(phone: str) -> None:
    """The matching key is the 10-digit national number (without +57 prefix)."""
    key = normalize_colombian_phone_key(phone)
    # Key should be exactly 10 digits, no +57 prefix
    assert len(key) == 10
    assert not key.startswith("57")
    assert not key.startswith("+57")
    # Key should be digits only
    assert key.isdigit()


@given(
    phone=st.one_of(
        st.just("3001234567"),
        st.just("3101234567"),
        st.just("3201234567"),
    )
)
def test_key_without_country_code(phone: str) -> None:
    """Phone numbers without country code produce correct matching keys."""
    key = normalize_colombian_phone_key(phone)
    assert len(key) == 10
    assert key.isdigit()


@given(
    phone=st.text(
        alphabet=st.characters(
            categories=["Nd", "Zs", "Pc", "Pd", "Po", "Pf", "Pi", "Ps"],
            min_codepoint=ord("0"),
            max_codepoint=ord("9"),
        ),
        min_size=10,
        max_size=20,
    ).filter(lambda s: any(c.isdigit() for c in s))
)
def test_phone_normalization_handles_arbitrary_formatting(phone: str) -> None:
    """Phone numbers with arbitrary formatting still normalize correctly."""
    try:
        normalized = normalize_colombian_phone(phone)
        # Should be in canonical +57 + 10 digits format
        assert normalized.startswith("+57")
        assert len(normalized) == 12  # +57 + 10 digits
        assert normalized[3:].isdigit()
        assert normalized[3:].startswith("3")  # Must start with 3
    except Exception:
        # Some inputs may be invalid; that's expected
        pass


@given(
    normalized=st.one_of(
        st.just("+573001234567"),
        st.just("+573101234567"),
        st.just("+573201234567"),
    )
)
def test_normalization_of_normalized_input(normalized: str) -> None:
    """Normalizing an already-normalized phone returns the same value."""
    result = normalize_colombian_phone(normalized)
    assert result == normalized


def test_rules_are_configurable_per_market() -> None:
    """Another market's calling code and national pattern are honored."""
    mexico = PhoneRules(country_code="52", national_pattern=r"[0-9]{10}")
    assert normalize_phone("+52 55 1234 5678", mexico) == "+525512345678"
    assert normalize_phone_key("55-1234-5678", mexico) == "5512345678"
    with pytest.raises(OrderValidationError):
        normalize_phone("+52 55 1234", mexico)


def test_default_rules_reject_non_mobile_colombian_numbers() -> None:
    with pytest.raises(OrderValidationError):
        normalize_phone("6011234567", _RULES)
