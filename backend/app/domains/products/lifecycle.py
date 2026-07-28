"""Product lifecycle transition graph (Requirements 2.11-2.14, 2.17, 2.19-2.21).

Pure functions that compute the next status for a requested transition,
raising a domain error without mutating anything when the transition is
illegal. `ProductLifecycleService` is responsible for actually persisting
the result.

Legal transitions:
    paused  --activate--> active
    active  --pause-----> paused
    active | paused --retire--> retired

Illegal transitions (all rejected without mutation):
    activating an already-active or a retired product
    pausing an already-paused or a retired product
    retiring an already-retired product
    activating or editing any retired product through normal operations
"""

from __future__ import annotations

from app.domains.products.errors import InvalidProductTransitionError, RetiredProductError


def _reject_if_retired(product_id: int, current_status: str) -> None:
    if current_status == "retired":
        raise RetiredProductError(product_id)


def next_status_on_activate(product_id: int, current_status: str) -> str:
    """Return `active` iff `current_status` is `paused`; otherwise raise."""
    _reject_if_retired(product_id, current_status)
    if current_status != "paused":
        raise InvalidProductTransitionError(current_status, "activate")
    return "active"


def next_status_on_pause(product_id: int, current_status: str) -> str:
    """Return `paused` iff `current_status` is `active`; otherwise raise."""
    _reject_if_retired(product_id, current_status)
    if current_status != "active":
        raise InvalidProductTransitionError(current_status, "pause")
    return "paused"


def next_status_on_retire(product_id: int, current_status: str) -> str:
    """Return `retired` iff `current_status` is `active` or `paused`.

    Retiring an already-retired product is illegal (no-op through the
    normal lifecycle operation, though the underlying Soft_Deletion
    guarantee is preserved regardless — see Requirement 2.21).
    """
    if current_status == "retired":
        raise InvalidProductTransitionError(current_status, "retire")
    return "retired"
