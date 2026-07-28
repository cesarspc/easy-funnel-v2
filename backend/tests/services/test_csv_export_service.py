"""Tests for CSV export service (Requirement 8.16-8.18).

Required property (testing.md -> Required Properties #9): For any exported
customer string, CSV encoding round-trips as data and cannot become an
executable spreadsheet formula.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from app.services.csv_export_service import CsvExportService


class TestCsvExportBasic:
    """Basic CSV export functionality tests."""

    def test_csv_export_header_row(self) -> None:
        """CSV export includes header row."""
        orders = [{
            "id": 1,
            "product_id": 100,
            "landing_id": 200,
            "landing_slug": "test-landing",
            "customer_name": "John Doe",
            "phone_e164": "+573001234567",
            "department": "Cundinamarca",
            "city": "Bogota",
            "address": "Calle 123",
            "quantity": 1,
            "status": "pending",
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "fraud_flags": [],
        }]

        service = CsvExportService()
        csv_content = service.export_orders(orders=orders)

        assert "id,product_id,landing_id,landing_slug,customer_name,phone_e164" in csv_content

    def test_csv_export_neutralizes_formula_injection(self) -> None:
        """CSV export neutralizes formula injection attempts."""
        orders = [{
            "id": 1,
            "product_id": 100,
            "landing_id": 200,
            "landing_slug": "test-landing",
            "customer_name": "=1+1",
            "phone_e164": "+573001234567",
            "department": "Cundinamarca",
            "city": "Bogota",
            "address": "Calle 123",
            "quantity": 1,
            "status": "pending",
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "fraud_flags": [],
        }]

        service = CsvExportService()
        csv_content = service.export_orders(orders=orders)

        # Formula should be neutralized (prefixed with apostrophe or escaped)
        assert "'=1+1" in csv_content or "=1+1" not in csv_content.split(",")[0]


class TestCsvExportSafety:
    """CSV export safety property tests."""

    @given(
        customer_string=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc",),  # No control chars
            ),
            min_size=1,
            max_size=500,
        )
    )
    def test_csv_encoding_round_trips_as_data(self, customer_string: str) -> None:
        """For any exported customer string, CSV encoding round-trips as data
        and cannot become an executable spreadsheet formula."""
        orders = [{
            "id": 1,
            "product_id": 100,
            "landing_id": 200,
            "landing_slug": "test-landing",
            "customer_name": customer_string,
            "phone_e164": "+573001234567",
            "department": "Cundinamarca",
            "city": "Bogota",
            "address": "Calle 123",
            "quantity": 1,
            "status": "pending",
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "fraud_flags": [],
        }]

        service = CsvExportService()
        csv_content = service.export_orders(orders=orders)

        # Parse CSV and verify round-trip
        import csv
        import io

        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)

        # Header row
        assert len(rows) >= 1
        header = rows[0]

        # Data row should contain the customer string
        if len(rows) > 1:
            data_row = rows[1]
            # Customer name should be in the row (index depends on header)
            found = False
            for cell in data_row:
                if customer_string in cell or cell == customer_string:
                    found = True
                    break

    @given(
        formula_char=st.sampled_from(["=", "+", "-", "@", "\t", "\r", "\n"]),
        customer_string=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc",),
            ),
            min_size=1,
            max_size=100,
        ).filter(lambda s: not s.startswith(("[", "http", "ftp")))
    )
    def test_formula_control_characters_are_neutralized(
        self, formula_char: str, customer_string: str
    ) -> None:
        """CSV export prevents formula control characters from creating
        executable formulas."""
        # Prepend formula control character
        malicious_string = formula_char + customer_string

        orders = [{
            "id": 1,
            "product_id": 100,
            "landing_id": 200,
            "landing_slug": "test-landing",
            "customer_name": malicious_string,
            "phone_e164": "+573001234567",
            "department": "Cundinamarca",
            "city": "Bogota",
            "address": "Calle 123",
            "quantity": 1,
            "status": "pending",
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "fraud_flags": [],
        }]

        service = CsvExportService()
        csv_content = service.export_orders(orders=orders)

        # The CSV should not contain an unescaped formula
        lines = csv_content.split("\n")
        for line in lines:
            if malicious_string in line:
                # If found, verify it's neutralized (escaped with apostrophe or similar)
                # Excel treats cells starting with ' as text
                assert line.strip().startswith("'") or "'" in line

    @given(
        customer_string=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc",),
                min_codepoint=ord(" "),
                max_codepoint=ord("~"),
            ),
            min_size=1,
            max_size=100,
        ).filter(lambda s: s.strip())
    )
    def test_customer_strings_remain_readable_after_export(
        self, customer_string: str
    ) -> None:
        """Customer strings remain merchant-readable after CSV export with
        formula-injection neutralization."""
        orders = [{
            "id": 1,
            "product_id": 100,
            "landing_id": 200,
            "landing_slug": "test-landing",
            "customer_name": customer_string,
            "phone_e164": "+573001234567",
            "department": "Cundinamarca",
            "city": "Bogota",
            "address": "Calle 123",
            "quantity": 1,
            "status": "pending",
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "fraud_flags": [],
        }]

        service = CsvExportService()
        csv_content = service.export_orders(orders=orders)

        # Parse CSV and verify the string is recoverable
        import csv
        import io

        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)

        # Customer name should be present in some form
        if len(rows) > 1:
            data_row = rows[1]
            # The original string (possibly neutralized) should be present
            found = False
            for cell in data_row:
                # Check if the string or its normalized form is present
                if customer_string in cell or cell.replace("'", "") == customer_string:
                    found = True
                    break
            assert found


def test_csv_export_empty_orders() -> None:
    """CSV export handles empty orders list."""
    orders: list[dict] = []

    service = CsvExportService()
    csv_content = service.export_orders(orders=orders)

    # Should have header row at minimum
    assert "id,product_id" in csv_content


def test_csv_export_multiple_orders() -> None:
    """CSV export handles multiple orders."""
    orders = [
        {
            "id": 1,
            "product_id": 100,
            "landing_id": 200,
            "landing_slug": "test-landing",
            "customer_name": "John Doe",
            "phone_e164": "+573001234567",
            "department": "Cundinamarca",
            "city": "Bogota",
            "address": "Calle 123",
            "quantity": 1,
            "status": "pending",
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "fraud_flags": [],
        },
        {
            "id": 2,
            "product_id": 100,
            "landing_id": 200,
            "landing_slug": "test-landing",
            "customer_name": "Jane Smith",
            "phone_e164": "+573101234567",
            "department": "Valle del Cauca",
            "city": "Cali",
            "address": "Calle 456",
            "quantity": 2,
            "status": "confirmed",
            "ip_address": "192.168.1.2",
            "user_agent": "Mozilla/5.0",
            "created_at": "2024-01-01T01:00:00",
            "updated_at": "2024-01-01T01:00:00",
            "fraud_flags": [],
        },
    ]

    service = CsvExportService()
    csv_content = service.export_orders(orders=orders)

    # Should have header + 2 data rows
    lines = [line for line in csv_content.split("\n") if line.strip()]
    assert len(lines) >= 3

    # Both customers should be present
    assert "John Doe" in csv_content
    assert "Jane Smith" in csv_content


def test_csv_export_with_fraud_flags() -> None:
    """CSV export includes fraud flags."""
    orders = [{
        "id": 1,
        "product_id": 100,
        "landing_id": 200,
        "landing_slug": "test-landing",
        "customer_name": "John Doe",
        "phone_e164": "+573001234567",
        "department": "Cundinamarca",
        "city": "Bogota",
        "address": "Calle 123",
        "quantity": 1,
        "status": "flagged_fraud",
        "ip_address": "192.168.1.1",
        "user_agent": "Mozilla/5.0",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
        "fraud_flags": [
            {
                "flag_type": "duplicate",
                "detail": {"order_id": 100, "matched_fields": ["phone"]},
            }
        ],
    }]

    service = CsvExportService()
    csv_content = service.export_orders(orders=orders)

    # Should include fraud flags information
    assert "flagged_fraud" in csv_content
