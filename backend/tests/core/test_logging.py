"""Unit tests for log redaction (Requirement 10.5).

Captures actual rendered log output (not just filter internals) so these
tests fail if redaction is ever accidentally bypassed by a formatting
change.
"""

from __future__ import annotations

import logging

from app.core.logging import RedactionFilter, StructuredFormatter


def _capture(record_kwargs: dict[str, object]) -> str:
    logger = logging.getLogger("test.redaction")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for h in list(logger.handlers):
        logger.removeHandler(h)

    stream_holder: list[str] = []

    class _CapturingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            stream_holder.append(self.format(record))

    handler = _CapturingHandler()
    handler.setFormatter(StructuredFormatter("%(message)s"))
    handler.addFilter(RedactionFilter())
    logger.addHandler(handler)

    message = record_kwargs.pop("message", "log message")
    logger.info(message, extra=record_kwargs)  # type: ignore[arg-type]

    return stream_holder[0] if stream_holder else ""


class TestRedactionFilter:
    def test_password_field_is_redacted(self) -> None:
        output = _capture({"password": "super-secret-password"})

        assert "super-secret-password" not in output
        assert "REDACTED" in output

    def test_jwt_field_is_redacted(self) -> None:
        output = _capture({"jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"})

        assert "eyJhbGciOiJIUzI1NiJ9" not in output

    def test_database_url_field_is_redacted(self) -> None:
        output = _capture({"database_url": "postgresql://user:pass@host/db"})

        assert "user:pass" not in output

    def test_full_address_field_is_redacted(self) -> None:
        output = _capture({"address": "Calle 123 #45-67, Apto 8B"})

        assert "Calle 123" not in output

    def test_jwt_shaped_substring_in_message_is_redacted_even_without_field_name(
        self,
    ) -> None:
        output = _capture(
            {"message": "issued token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature-value"}
        )

        assert "eyJhbGciOiJIUzI1NiJ9" not in output

    def test_connection_string_shaped_substring_in_message_is_redacted(self) -> None:
        output = _capture({"message": "connecting to postgresql://admin:hunter2@db.example/prod"})

        assert "hunter2" not in output

    def test_non_sensitive_fields_pass_through_unredacted(self) -> None:
        output = _capture({"order_id": 42, "status": "pending"})

        assert "42" in output
        assert "pending" in output

    def test_nested_dict_values_are_redacted(self) -> None:
        output = _capture({"customer": {"phone": "+573001234567", "quantity": 2}})

        assert "+573001234567" not in output
        assert "2" in output
