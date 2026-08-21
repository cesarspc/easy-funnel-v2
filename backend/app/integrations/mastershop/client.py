"""Bounded HTTP transport for MasterShop's create-order endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class MastershopHttpResult:
    status_code: int
    body: Any


class MastershopTransport(Protocol):
    async def create_order(self, payload: dict[str, Any]) -> MastershopHttpResult:
        ...


class MastershopClient:
    """Send one order without ever exposing the API key outside the backend."""

    def __init__(
        self,
        *,
        api_key: str,
        orders_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._orders_url = orders_url
        self._timeout = timeout_seconds
        self._transport = transport

    async def create_order(self, payload: dict[str, Any]) -> MastershopHttpResult:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(
                self._orders_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "ms-api-key": self._api_key,
                },
            )

        # Keep provider diagnostics bounded so an unexpected HTML/error page
        # cannot grow the synchronization table without limit.
        raw = response.text
        truncated = len(response.content) > 65_536
        bounded = raw[:65_536]
        if truncated:
            # Do not parse an unexpectedly large provider response into an
            # unbounded object just to persist diagnostics.
            body: Any = {"raw": bounded, "truncated": True}
        else:
            try:
                body = response.json()
            except ValueError:
                body = {"raw": bounded, "truncated": False}
        return MastershopHttpResult(status_code=response.status_code, body=body)
