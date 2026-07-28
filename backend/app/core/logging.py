"""Structured logging with redaction filters (Requirement 10.5).

Application logs must never contain passwords, JWT values, database/Redis/R2
credentials, full customer addresses, or full sensitive Order records. This
module provides a `logging.Filter` that redacts known-sensitive field names
from structured `extra=` log payloads plus a best-effort regex pass over the
rendered message for JWTs and connection-string-style credentials, so a
single misused `logger.info(f"...{token}...")` does not leak a secret.

Usage:
    from app.core.logging import configure_logging
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("order.created", extra={"order_id": 1, "phone": "+573001234567"})
"""

from __future__ import annotations

import logging
import re
import sys

# Field names (case-insensitive) that must never appear in log output,
# whether passed via `extra=` or nested inside a dict/list value.
_REDACTED_FIELD_NAMES = frozenset(
    {
        "password",
        "password_hash",
        "jwt",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "jwt_secret",
        "authorization",
        "database_url",
        "connection_string",
        "r2_secret_access_key",
        "r2_access_key_id",
        "upstash_redis_rest_token",
        "address",
        "customer_name",
        "phone",
        "phone_e164",
        "phone_normalized_key",
    }
)

_REDACTED = "***REDACTED***"

# Best-effort patterns for secrets that might end up concatenated directly
# into a rendered log message rather than passed as a structured field.
_JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_CONNECTION_STRING_PATTERN = re.compile(
    r"(postgres(?:ql)?|redis|rediss)://[^:\s]+:[^@\s]+@[^\s]+", re.IGNORECASE
)


def _redact_value(key: str, value: object) -> object:
    if key.lower() in _REDACTED_FIELD_NAMES:
        return _REDACTED
    if isinstance(value, dict):
        return {k: _redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    return value


def _redact_text(text: str) -> str:
    text = _JWT_PATTERN.sub(_REDACTED, text)
    text = _CONNECTION_STRING_PATTERN.sub(_REDACTED, text)
    return text


class RedactionFilter(logging.Filter):
    """Redacts sensitive field names and secret-shaped substrings in-place."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_text(str(record.msg))

        for key, value in list(record.__dict__.items()):
            if key in _REDACTED_FIELD_NAMES or isinstance(value, (dict, list)):
                record.__dict__[key] = _redact_value(key, value)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact_value(str(k), v) for k, v in record.args.items()}
            else:
                record.args = tuple(
                    _redact_text(arg) if isinstance(arg, str) else arg for arg in record.args
                )

        return True


# Attributes present on every LogRecord that are not caller-supplied
# structured fields (i.e. not passed via `extra=`) and so are excluded when
# rendering the structured-field payload.
_STANDARD_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


class StructuredFormatter(logging.Formatter):
    """Renders the log message plus any `extra=` fields as `key=value` pairs.

    Runs after `RedactionFilter` has already redacted `record.__dict__`, so
    the rendered output reflects the redacted values.
    """

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extra_fields = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_ATTRS
        }
        if not extra_fields:
            return base
        rendered_extras = " ".join(f"{key}={value!r}" for key, value in extra_fields.items())
        return f"{base} {rendered_extras}"


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging with the redaction filter attached.

    Idempotent: safe to call multiple times (e.g. once per test) without
    stacking duplicate handlers.
    """
    root = logging.getLogger()
    root.setLevel(level)

    for existing_handler in list(root.handlers):
        root.removeHandler(existing_handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(StructuredFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactionFilter())
    root.addHandler(handler)
