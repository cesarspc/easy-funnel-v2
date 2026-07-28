"""Unit + property tests for banner ordering (Requirements 3.5-3.8).

Required property (design.md -> Testing Strategy): for any banner list and
valid reorder operation, order indexes are unique and the rendered
sequence is a permutation of the same banners.
"""

from __future__ import annotations

import pytest
from app.domains.landings.banner_ordering import (
    MAX_BANNERS_PER_LANDING,
    contiguous_indices,
    next_append_index,
    reorder,
    validate_can_add_banner,
)
from app.domains.landings.errors import BannerLimitExceededError, LandingValidationError
from hypothesis import given
from hypothesis import strategies as st


class TestValidateCanAddBanner:
    def test_below_the_cap_is_allowed(self) -> None:
        validate_can_add_banner(14, landing_id=1)  # does not raise

    def test_at_the_cap_is_rejected(self) -> None:
        with pytest.raises(BannerLimitExceededError):
            validate_can_add_banner(MAX_BANNERS_PER_LANDING, landing_id=1)

    def test_above_the_cap_is_rejected(self) -> None:
        with pytest.raises(BannerLimitExceededError):
            validate_can_add_banner(MAX_BANNERS_PER_LANDING + 1, landing_id=1)


class TestNextAppendIndex:
    def test_first_banner_gets_index_zero(self) -> None:
        assert next_append_index(0) == 0

    def test_nth_banner_gets_index_n(self) -> None:
        assert next_append_index(5) == 5


class TestReorder:
    def test_moving_the_first_item_to_the_end(self) -> None:
        assert reorder([1, 2, 3], 0, 2) == [2, 3, 1]

    def test_moving_the_last_item_to_the_start(self) -> None:
        assert reorder([1, 2, 3], 2, 0) == [3, 1, 2]

    def test_empty_sequence_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            reorder([], 0, 0)

    def test_out_of_range_from_index_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            reorder([1, 2, 3], 5, 0)

    def test_out_of_range_to_index_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError):
            reorder([1, 2, 3], 0, 5)


class TestContiguousIndices:
    def test_maps_each_id_to_its_position(self) -> None:
        assert contiguous_indices([10, 20, 30]) == {10: 0, 20: 1, 30: 2}

    def test_empty_sequence_maps_to_empty_dict(self) -> None:
        assert contiguous_indices([]) == {}


# Unique, small integer ids representing banners in a landing.
_banner_id_lists = st.lists(
    st.integers(min_value=1, max_value=10_000), min_size=1, max_size=15, unique=True
)


@given(banner_ids=_banner_id_lists)
def test_contiguous_indices_are_unique_and_gap_free(banner_ids: list[int]) -> None:
    """Property: for any banner list, renumbering yields unique, contiguous
    indices covering exactly 0..n-1."""
    indices = contiguous_indices(banner_ids)

    assert sorted(indices.values()) == list(range(len(banner_ids)))
    assert len(set(indices.values())) == len(indices)


@given(
    banner_ids=_banner_id_lists,
    from_index=st.integers(min_value=0),
    to_index=st.integers(min_value=0),
)
def test_reorder_yields_a_permutation_of_the_same_banners(
    banner_ids: list[int], from_index: int, to_index: int
) -> None:
    """Property (design.md): for any banner list and valid reorder
    operation, the rendered sequence is a permutation of the same banners,
    and renumbering it yields unique contiguous indices."""
    if from_index >= len(banner_ids) or to_index >= len(banner_ids):
        return  # invalid operation for this input; not under test here

    result = reorder(banner_ids, from_index, to_index)

    assert sorted(result) == sorted(banner_ids)
    assert len(result) == len(set(result))
    indices = contiguous_indices(result)
    assert sorted(indices.values()) == list(range(len(result)))
