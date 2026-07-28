"""Dashboard rate computation (Requirements 8.12, 8.13, 8.21).

Conversion_Rate is orders over views and Flagged_Fraud_Rate is flagged orders
over total orders; both return zero rather than dividing by zero.
"""

from __future__ import annotations

from app.domains.analytics.rates import conversion_rate, flagged_fraud_rate
from hypothesis import given
from hypothesis import strategies as st


class TestConversionRate:
    def test_is_orders_divided_by_views(self) -> None:
        assert conversion_rate(orders=5, views=20) == 0.25

    def test_is_zero_when_there_are_no_views(self) -> None:
        assert conversion_rate(orders=0, views=0) == 0.0

    def test_is_zero_when_orders_exist_without_recorded_views(self) -> None:
        # Zero-guarded denominator, not an inverted ratio: an order with no
        # recorded view cannot produce an infinite or inverted rate.
        assert conversion_rate(orders=3, views=0) == 0.0

    def test_is_zero_when_there_are_no_orders(self) -> None:
        assert conversion_rate(orders=0, views=40) == 0.0

    @given(
        views=st.integers(min_value=1, max_value=10_000),
        orders=st.integers(min_value=0, max_value=10_000),
    )
    def test_never_exceeds_one_when_orders_do_not_exceed_views(
        self, views: int, orders: int
    ) -> None:
        rate = conversion_rate(orders=min(orders, views), views=views)

        assert 0.0 <= rate <= 1.0


class TestFlaggedFraudRate:
    def test_is_flagged_divided_by_total(self) -> None:
        assert flagged_fraud_rate(flagged_orders=1, total_orders=4) == 0.25

    def test_is_zero_when_there_are_no_orders(self) -> None:
        assert flagged_fraud_rate(flagged_orders=0, total_orders=0) == 0.0

    def test_is_one_when_every_order_is_flagged(self) -> None:
        assert flagged_fraud_rate(flagged_orders=7, total_orders=7) == 1.0

    @given(total=st.integers(min_value=1, max_value=10_000), flagged=st.integers(min_value=0))
    def test_never_exceeds_one_for_a_subset_of_orders(self, total: int, flagged: int) -> None:
        rate = flagged_fraud_rate(flagged_orders=min(flagged, total), total_orders=total)

        assert 0.0 <= rate <= 1.0
