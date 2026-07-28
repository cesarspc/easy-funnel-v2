"""Unit tests for the product lifecycle transition graph (Requirements
2.11-2.14, 2.17, 2.19-2.21)."""

from __future__ import annotations

import pytest
from app.domains.products.errors import InvalidProductTransitionError, RetiredProductError
from app.domains.products.lifecycle import (
    next_status_on_activate,
    next_status_on_pause,
    next_status_on_retire,
)


class TestNextStatusOnActivate:
    def test_paused_to_active_is_legal(self) -> None:
        assert next_status_on_activate(1, "paused") == "active"

    def test_activating_an_already_active_product_is_rejected(self) -> None:
        with pytest.raises(InvalidProductTransitionError):
            next_status_on_activate(1, "active")

    def test_activating_a_retired_product_is_rejected(self) -> None:
        with pytest.raises(RetiredProductError):
            next_status_on_activate(1, "retired")


class TestNextStatusOnPause:
    def test_active_to_paused_is_legal(self) -> None:
        assert next_status_on_pause(1, "active") == "paused"

    def test_pausing_an_already_paused_product_is_rejected(self) -> None:
        with pytest.raises(InvalidProductTransitionError):
            next_status_on_pause(1, "paused")

    def test_pausing_a_retired_product_is_rejected(self) -> None:
        with pytest.raises(RetiredProductError):
            next_status_on_pause(1, "retired")


class TestNextStatusOnRetire:
    def test_active_to_retired_is_legal(self) -> None:
        assert next_status_on_retire(1, "active") == "retired"

    def test_paused_to_retired_is_legal(self) -> None:
        assert next_status_on_retire(1, "paused") == "retired"

    def test_retiring_an_already_retired_product_is_rejected(self) -> None:
        with pytest.raises(InvalidProductTransitionError):
            next_status_on_retire(1, "retired")
