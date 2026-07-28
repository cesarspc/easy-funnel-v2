"""Banner ordering rules (Requirements 3.5, 3.6, 3.7, 3.8).

Banners are represented here purely by their integer ids; order is encoded
as the position of an id within a sequence. Recomputing contiguous
0-based indices from a sequence handles reordering and gap-closing with
the same operation: whatever sequence of ids results (after a move or a
removal), renumbering it 0..n-1 always yields unique, contiguous indices.
"""

from __future__ import annotations

from app.domains.landings.errors import BannerLimitExceededError, LandingValidationError

MAX_BANNERS_PER_LANDING = 15


def validate_can_add_banner(current_count: int, landing_id: int) -> None:
    """Raise if adding one more banner would exceed the 15-banner cap."""
    if current_count >= MAX_BANNERS_PER_LANDING:
        raise BannerLimitExceededError(landing_id)


def next_append_index(current_count: int) -> int:
    """Return the order index for a banner appended to a landing with
    `current_count` existing banners."""
    return current_count


def reorder(banner_ids: list[int], from_index: int, to_index: int) -> list[int]:
    """Move the id at `from_index` to `to_index`; return the new id sequence.

    The result is always a permutation of `banner_ids` (Requirement 3.7);
    callers renumber the returned sequence with `contiguous_indices`.
    """
    if not banner_ids:
        raise LandingValidationError("order_index", "Cannot reorder an empty banner sequence.")
    if not (0 <= from_index < len(banner_ids)) or not (0 <= to_index < len(banner_ids)):
        raise LandingValidationError("order_index", "Reorder index is out of range.")

    ids = list(banner_ids)
    item = ids.pop(from_index)
    ids.insert(to_index, item)
    return ids


def contiguous_indices(ordered_banner_ids: list[int]) -> dict[int, int]:
    """Map each banner id to its contiguous ascending 0-based index.

    Applying this to any sequence — the result of a reorder, or the
    remaining ids after a removal — always yields unique, gap-free
    positions (Requirements 3.7, 3.8).
    """
    return {banner_id: index for index, banner_id in enumerate(ordered_banner_ids)}
