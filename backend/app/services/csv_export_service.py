"""CsvExportService with formula-injection neutralization (Requirement 8.17-8.18).

Exports orders to CSV with:
- Header row
- Spreadsheet-import encoding (comma-separated, quoted fields)
- Formula-injection neutralization: any value beginning with =, +, -, @, tab, or CR
  is prefixed with a non-executable string while remaining readable
- Atomic failure: no partial file on encoding failure

The neutralization prefixes problematic values with a single quote (')
which causes spreadsheets to treat them as text rather than formulas,
but the content remains merchant-readable.
"""

from __future__ import annotations

import csv
import io
from typing import Any

# Formula control characters that must be neutralized
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def neutralize_formula(value: str) -> str:
    """Neutralize a value that might be interpreted as a spreadsheet formula.

    Prefixes values starting with formula control characters with a single
    quote, causing spreadsheets to treat them as text while keeping them
    merchant-readable.
    """
    if not value:
        return value
    if value.startswith(_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def escape_csv_value(value: str) -> str:
    """Escape a value for CSV output with neutralization.

    - Formula-injection values are neutralized with a leading apostrophe
    - CSV quoting and quote-doubling is handled by csv.writer
    """
    if value is None:
        return ""
    
    return neutralize_formula(str(value))


class CsvExportService:
    """Service to export orders to CSV with formula-injection neutralization."""

    def export_orders(
        self,
        orders: list[dict[str, Any]],
    ) -> str:
        """Export orders to CSV with neutralization.

        Args:
            orders: List of order dicts with fields:
                - id, product_id, landing_id, landing_slug
                - customer_name, phone_e164, department, city, address
                - quantity, status, ip_address, user_agent
                - created_at, updated_at
                - fraud_flags (optional list of flag dicts)

        Returns:
            CSV string with header row and neutralized values

        Raises:
            ValueError: If export fails atomically (no partial file)
        """
        try:
            output = io.StringIO()
            writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

            # Header row (Requirement 8.16)
            headers = [
                "order_id",
                "product_id",
                "landing_id",
                "landing_slug",
                "customer_name",
                "phone_e164",
                "department",
                "city",
                "address",
                "quantity",
                "status",
                "ip_address",
                "user_agent",
                "created_at",
                "updated_at",
                "fraud_flags",
            ]
            writer.writerow(headers)

            # Data rows
            for order in orders:
                fraud_flags = order.get("fraud_flags", [])
                flags_text = self._format_fraud_flags(fraud_flags)

                row = [
                    str(order.get("id", "")),
                    str(order.get("product_id", "")),
                    str(order.get("landing_id", "")),
                    escape_csv_value(order.get("landing_slug", "")),
                    escape_csv_value(order.get("customer_name", "")),
                    escape_csv_value(order.get("phone_e164", "")),
                    escape_csv_value(order.get("department", "")),
                    escape_csv_value(order.get("city", "")),
                    escape_csv_value(order.get("address", "")),
                    str(order.get("quantity", "")),
                    escape_csv_value(order.get("status", "")),
                    escape_csv_value(order.get("ip_address", "")),
                    escape_csv_value(order.get("user_agent", "")),
                    self._format_datetime(order.get("created_at")),
                    self._format_datetime(order.get("updated_at")),
                    flags_text,
                ]
                writer.writerow(row)

            return output.getvalue()

        except Exception as exc:
            # Fail atomically - no partial file
            raise ValueError(f"CSV export failed: {exc}") from exc

    def _format_fraud_flags(self, flags: list[dict[str, Any]]) -> str:
        """Format fraud flags as a readable string."""
        if not flags:
            return ""
        
        flag_strings = []
        for flag in flags:
            flag_type = flag.get("flag_type", "unknown")
            detail = flag.get("detail", {})
            
            if flag_type == "duplicate":
                matched = detail.get("matched_fields", [])
                window = detail.get("window_hours", 0)
                flag_strings.append(f"duplicate(fields={matched},window={window}h)")
            elif flag_type == "blacklist":
                entry_type = detail.get("entry_type", "unknown")
                reason = detail.get("reason", "")
                flag_strings.append(f"blacklist({entry_type}:{reason})")
            elif flag_type == "rate_limit_phone":
                count = detail.get("count", 0)
                limit = detail.get("limit", 0)
                flag_strings.append(f"rate_limit_phone(count={count}/{limit})")
            elif flag_type == "rate_limit_ip":
                count = detail.get("count", 0)
                limit = detail.get("limit", 0)
                flag_strings.append(f"rate_limit_ip(count={count}/{limit})")
            elif flag_type == "geoip":
                location = detail.get("location_code", "unknown")
                action = detail.get("action", "unknown")
                flag_strings.append(f"geoip({location}:{action})")
            else:
                flag_strings.append(f"{flag_type}")

        return "; ".join(flag_strings)

    def _format_datetime(self, dt: Any) -> str:
        """Format datetime as ISO 8601 string."""
        if dt is None:
            return ""
        if isinstance(dt, str):
            return dt
        return dt.isoformat()
