"""Unit tests for request-context extraction (Requirements 5.10, 5.11)."""

from __future__ import annotations

from app.core.request_context import (
    USER_AGENT_MAX_LENGTH,
    extract_client_ip,
    get_request_context,
    truncate_user_agent,
)
from starlette.datastructures import Headers
from starlette.requests import Request


def _make_request(headers: dict[str, str], *, client_host: str | None = "127.0.0.1") -> Request:
    scope: dict[str, object] = {
        "type": "http",
        "headers": Headers(headers).raw,
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


class TestTruncateUserAgent:
    def test_value_at_exactly_the_limit_is_preserved(self) -> None:
        value = "a" * USER_AGENT_MAX_LENGTH

        result = truncate_user_agent(value)

        assert result == value
        assert len(result) == USER_AGENT_MAX_LENGTH

    def test_value_over_the_limit_is_truncated_not_rejected(self) -> None:
        value = "a" * (USER_AGENT_MAX_LENGTH + 1)

        result = truncate_user_agent(value)

        assert len(result) == USER_AGENT_MAX_LENGTH
        assert result == "a" * USER_AGENT_MAX_LENGTH

    def test_value_under_the_limit_is_unchanged(self) -> None:
        value = "Mozilla/5.0"

        assert truncate_user_agent(value) == value


class TestExtractClientIp:
    def test_prefers_cf_connecting_ip_header(self) -> None:
        request = _make_request({"cf-connecting-ip": "203.0.113.5", "x-forwarded-for": "10.0.0.1"})

        assert extract_client_ip(request) == "203.0.113.5"

    def test_falls_back_to_x_forwarded_for_first_hop(self) -> None:
        request = _make_request({"x-forwarded-for": "203.0.113.5, 10.0.0.1"})

        assert extract_client_ip(request) == "203.0.113.5"

    def test_falls_back_to_raw_peer_address_when_no_headers_present(self) -> None:
        request = _make_request({}, client_host="192.168.1.1")

        assert extract_client_ip(request) == "192.168.1.1"

    def test_returns_unknown_when_no_source_is_available(self) -> None:
        request = _make_request({}, client_host=None)

        assert extract_client_ip(request) == "unknown"


class TestGetRequestContext:
    def test_captures_ip_and_truncated_user_agent(self) -> None:
        request = _make_request(
            {
                "cf-connecting-ip": "203.0.113.9",
                "user-agent": "a" * (USER_AGENT_MAX_LENGTH + 50),
            }
        )

        context = get_request_context(request)

        assert context.ip_address == "203.0.113.9"
        assert len(context.user_agent) == USER_AGENT_MAX_LENGTH

    def test_missing_user_agent_header_yields_empty_string(self) -> None:
        request = _make_request({"cf-connecting-ip": "203.0.113.9"})

        context = get_request_context(request)

        assert context.user_agent == ""
