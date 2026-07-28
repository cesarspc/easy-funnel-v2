"""Request-context extraction: client IP and user agent.

Requirements 5.10 / 5.11: capture the request user agent verbatim up to 512
characters, truncating (never rejecting) longer values. Design.md -> core:
extract the client IP from the trusted Cloudflare/Koyeb forwarded header
rather than the raw peer address, since the backend sits behind Cloudflare's
edge and Koyeb's proxy.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

USER_AGENT_MAX_LENGTH = 512

# Cloudflare sets this header to the true client IP at its edge; it is more
# reliable than X-Forwarded-For (which can carry a chain of proxy hops) for
# this single-hop Cloudflare -> Koyeb topology.
_CF_CONNECTING_IP_HEADER = "cf-connecting-ip"
# Fallback for local/non-Cloudflare environments (e.g. Koyeb's own proxy, or
# local development): first hop of X-Forwarded-For.
_X_FORWARDED_FOR_HEADER = "x-forwarded-for"


@dataclass(frozen=True)
class RequestContext:
    """Trusted request metadata captured for attribution and fraud evaluation."""

    ip_address: str
    user_agent: str


def truncate_user_agent(raw_user_agent: str) -> str:
    """Truncate a user-agent string to the stored maximum length.

    Never rejects the request (Requirement 5.11): values longer than
    `USER_AGENT_MAX_LENGTH` are truncated rather than causing a validation
    error.
    """
    return raw_user_agent[:USER_AGENT_MAX_LENGTH]


def extract_client_ip(request: Request) -> str:
    """Extract the client IP from the trusted edge-forwarded header.

    Falls back to `X-Forwarded-For`'s first hop, then to the raw ASGI peer
    address (local development without a proxy in front).
    """
    cf_ip = request.headers.get(_CF_CONNECTING_IP_HEADER)
    if cf_ip:
        return cf_ip.strip()

    forwarded_for = request.headers.get(_X_FORWARDED_FOR_HEADER)
    if forwarded_for:
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return first_hop

    if request.client is not None:
        return request.client.host

    return "unknown"


def get_request_context(request: Request) -> RequestContext:
    """FastAPI dependency returning the trusted IP + truncated user agent."""
    ip_address = extract_client_ip(request)
    raw_user_agent = request.headers.get("user-agent", "")
    return RequestContext(
        ip_address=ip_address,
        user_agent=truncate_user_agent(raw_user_agent),
    )
