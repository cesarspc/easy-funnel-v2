"""Unit + property tests for CTA placement (Requirements 3.9-3.15).

Required property (design.md -> Testing Strategy): for any valid CTA
configuration and 1-15 banner count, generated CTA positions satisfy the
selected mode and stay within the sequence.
"""

from __future__ import annotations

import pytest
from app.domains.landings.cta_placement import (
    CTA_MODE_AFTER_EVERY,
    CTA_MODE_EVERY_N,
    CTA_MODE_FIXED_POSITIONS,
    INTERVAL_MAX,
    INTERVAL_MIN,
    compute_cta_positions,
    validate_cta_config,
)
from app.domains.landings.errors import LandingValidationError
from hypothesis import given
from hypothesis import strategies as st


class TestValidateCtaConfigAfterEvery:
    def test_after_every_requires_no_extra_fields(self) -> None:
        config = validate_cta_config(CTA_MODE_AFTER_EVERY)
        assert config.mode == CTA_MODE_AFTER_EVERY
        assert config.interval is None
        assert config.positions is None


class TestValidateCtaConfigEveryN:
    def test_interval_within_range_is_accepted(self) -> None:
        config = validate_cta_config(CTA_MODE_EVERY_N, interval=3)
        assert config.interval == 3

    def test_interval_minimum_boundary_is_accepted(self) -> None:
        validate_cta_config(CTA_MODE_EVERY_N, interval=INTERVAL_MIN)

    def test_interval_maximum_boundary_is_accepted(self) -> None:
        validate_cta_config(CTA_MODE_EVERY_N, interval=INTERVAL_MAX)

    def test_missing_interval_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_cta_config(CTA_MODE_EVERY_N)
        assert exc_info.value.field == "cta_interval"

    def test_interval_below_minimum_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_cta_config(CTA_MODE_EVERY_N, interval=0)

    def test_interval_above_maximum_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_cta_config(CTA_MODE_EVERY_N, interval=16)


class TestValidateCtaConfigFixedPositions:
    def test_non_empty_unique_positions_are_accepted(self) -> None:
        config = validate_cta_config(CTA_MODE_FIXED_POSITIONS, positions=[2, 5, 8])
        assert config.positions == frozenset({2, 5, 8})

    def test_empty_positions_are_rejected(self) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_cta_config(CTA_MODE_FIXED_POSITIONS, positions=[])
        assert exc_info.value.field == "cta_positions"

    def test_none_positions_are_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_cta_config(CTA_MODE_FIXED_POSITIONS, positions=None)

    def test_duplicate_positions_are_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_cta_config(CTA_MODE_FIXED_POSITIONS, positions=[2, 2, 5])

    def test_zero_or_negative_position_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_cta_config(CTA_MODE_FIXED_POSITIONS, positions=[0, 3])

    def test_position_beyond_banner_count_is_rejected_when_checked(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_cta_config(CTA_MODE_FIXED_POSITIONS, positions=[2, 20], banner_count=5)

    def test_position_within_banner_count_is_accepted(self) -> None:
        validate_cta_config(CTA_MODE_FIXED_POSITIONS, positions=[2, 5], banner_count=5)


class TestValidateCtaConfigUnsupportedMode:
    def test_unsupported_mode_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            validate_cta_config("not_a_real_mode")
        assert exc_info.value.field == "cta_mode"


class TestComputeCtaPositionsAfterEvery:
    def test_one_cta_after_each_banner(self) -> None:
        config = validate_cta_config(CTA_MODE_AFTER_EVERY)
        assert compute_cta_positions(config, 5) == [1, 2, 3, 4, 5]

    def test_zero_banners_yields_no_ctas(self) -> None:
        config = validate_cta_config(CTA_MODE_AFTER_EVERY)
        assert compute_cta_positions(config, 0) == []


class TestComputeCtaPositionsEveryN:
    def test_cta_after_each_completed_interval(self) -> None:
        config = validate_cta_config(CTA_MODE_EVERY_N, interval=3)
        assert compute_cta_positions(config, 10) == [3, 6, 9]

    def test_no_cta_when_banner_count_is_below_the_interval(self) -> None:
        config = validate_cta_config(CTA_MODE_EVERY_N, interval=5)
        assert compute_cta_positions(config, 3) == []


class TestComputeCtaPositionsFixedPositions:
    def test_returns_configured_positions_in_ascending_order(self) -> None:
        config = validate_cta_config(CTA_MODE_FIXED_POSITIONS, positions=[8, 2, 5])
        assert compute_cta_positions(config, 10) == [2, 5, 8]

    def test_positions_beyond_the_current_banner_count_are_excluded(self) -> None:
        config = validate_cta_config(CTA_MODE_FIXED_POSITIONS, positions=[2, 5, 20])
        assert compute_cta_positions(config, 10) == [2, 5]


# --- Property tests -----------------------------------------------------

_banner_counts = st.integers(min_value=1, max_value=15)


@given(banner_count=_banner_counts)
def test_after_every_positions_always_match_the_banner_count(banner_count: int) -> None:
    config = validate_cta_config(CTA_MODE_AFTER_EVERY)

    positions = compute_cta_positions(config, banner_count)

    assert positions == list(range(1, banner_count + 1))
    assert all(1 <= p <= banner_count for p in positions)


@given(
    banner_count=_banner_counts,
    interval=st.integers(min_value=INTERVAL_MIN, max_value=INTERVAL_MAX),
)
def test_every_n_positions_are_multiples_of_interval_within_sequence(
    banner_count: int, interval: int
) -> None:
    config = validate_cta_config(CTA_MODE_EVERY_N, interval=interval)

    positions = compute_cta_positions(config, banner_count)

    assert all(p % interval == 0 for p in positions)
    assert all(1 <= p <= banner_count for p in positions)
    assert positions == sorted(positions)


@given(
    banner_count=_banner_counts,
    raw_positions=st.lists(st.integers(min_value=1, max_value=15), min_size=1, unique=True),
)
def test_fixed_positions_output_is_a_subset_within_sequence(
    banner_count: int, raw_positions: list[int]
) -> None:
    config = validate_cta_config(
        CTA_MODE_FIXED_POSITIONS, positions=raw_positions, banner_count=None
    )

    positions = compute_cta_positions(config, banner_count)

    assert set(positions).issubset(set(raw_positions))
    assert all(1 <= p <= banner_count for p in positions)
    assert positions == sorted(positions)
