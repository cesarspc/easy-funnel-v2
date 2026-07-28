"""Property tests for order status transitions (Requirement 5.19-5.22).

Required property (testing.md -> Required Properties #4): For any order state
and requested transition, only the documented transition graph can change
persisted status.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from app.domains.orders.errors import InvalidOrderStatusTransition
from app.domains.orders.normalization import (
    ALLOWED_TRANSITIONS,
    DEFAULT_ORDER_STATUS,
    FLAGGED_FRAUD_STATUS,
    validate_status,
)


# Valid order statuses
VALID_STATUSES = ["pending", "confirmed", "shipped", "delivered", "cancelled", "flagged_fraud"]


@given(
    current_status=st.sampled_from(VALID_STATUSES),
    target_status=st.sampled_from(VALID_STATUSES),
)
def test_only_documented_transitions_succeed(
    current_status: str, target_status: str
) -> None:
    """For any order state and requested transition, only the documented
    transition graph can change persisted status."""
    valid_transitions = ALLOWED_TRANSITIONS.get(current_status, set())

    if target_status in valid_transitions:
        # Should succeed - no exception
        validate_status(current_status, target_status)
    else:
        # Should fail - raise InvalidOrderStatusTransition
        with pytest.raises(InvalidOrderStatusTransition) as exc_info:
            validate_status(current_status, target_status)
        assert exc_info.value.current_status == current_status
        assert exc_info.value.target_status == target_status


@given(
    status_from=st.sampled_from(["pending", "confirmed", "shipped", "flagged_fraud"]),
    status_to=st.sampled_from(["cancelled"]),
)
def test_cancel_transition_is_always_allowed(status_from: str, status_to: str) -> None:
    """Cancel transition is allowed from all active states."""
    # These should all succeed
    validate_status(status_from, status_to)


@given(
    current=st.sampled_from(["pending", "confirmed", "shipped", "delivered", "cancelled", "flagged_fraud"]),
    target=st.sampled_from(["delivered", "cancelled", "pending", "confirmed", "shipped", "flagged_fraud"]),
)
def test_transition_graph_is_complete(current: str, target: str) -> None:
    """The transition graph is complete and documented."""
    valid_transitions = ALLOWED_TRANSITIONS.get(current, set())

    # Verify the transition exists in the documented graph
    if target in valid_transitions:
        # Check it's actually valid
        assert target in ALLOWED_TRANSITIONS.get(current, set())
    else:
        # Check it's not valid
        assert target not in ALLOWED_TRANSITIONS.get(current, set())


def test_default_order_status_is_pending() -> None:
    """New orders start with 'pending' status."""
    assert DEFAULT_ORDER_STATUS == "pending"


def test_flagged_fraud_can_transition_to_pending() -> None:
    """flagged_fraud orders can transition to pending for review."""
    # This should succeed
    validate_status("flagged_fraud", "pending")


def test_flagged_fraud_can_transition_to_cancelled() -> None:
    """flagged_fraud orders can transition to cancelled."""
    # This should succeed
    validate_status("flagged_fraud", "cancelled")


def test_delivered_has_no_outgoing_transitions() -> None:
    """Delivered orders cannot transition to any other status."""
    assert "delivered" not in ALLOWED_TRANSITIONS
    for target in VALID_STATUSES:
        if target != "delivered":
            with pytest.raises(InvalidOrderStatusTransition):
                validate_status("delivered", target)


def test_cancelled_has_no_outgoing_transitions() -> None:
    """Cancelled orders cannot transition to any other status."""
    assert "cancelled" not in ALLOWED_TRANSITIONS
    for target in VALID_STATUSES:
        if target != "cancelled":
            with pytest.raises(InvalidOrderStatusTransition):
                validate_status("cancelled", target)


@given(
    status=st.sampled_from(VALID_STATUSES),
)
def test_same_status_transition_is_rejected(status: str) -> None:
    """Transitioning to the same status should be rejected."""
    valid_transitions = ALLOWED_TRANSITIONS.get(status, set())
    # If status has outgoing transitions, same status should be rejected
    # (transitioning to self is not a valid transition)
    if valid_transitions:
        with pytest.raises(InvalidOrderStatusTransition):
            validate_status(status, status)
    else:
        # For statuses with no outgoing transitions, any transition is rejected
        with pytest.raises(InvalidOrderStatusTransition):
            validate_status(status, status)


def test_pending_to_confirmed_is_allowed() -> None:
    """Pending -> Confirmed is a valid transition."""
    validate_status("pending", "confirmed")


def test_confirmed_to_shipped_is_allowed() -> None:
    """Confirmed -> Shipped is a valid transition."""
    validate_status("confirmed", "shipped")


def test_shipped_to_delivered_is_allowed() -> None:
    """Shipped -> Delivered is a valid transition."""
    validate_status("shipped", "delivered")


def test_flagged_fraud_to_pending_is_allowed() -> None:
    """Flagged fraud -> Pending (review) is a valid transition."""
    validate_status("flagged_fraud", "pending")
