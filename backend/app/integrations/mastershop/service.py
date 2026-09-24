"""Durable, failure-isolated MasterShop order synchronization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from prisma import Json, Prisma

from app.integrations.mastershop.client import MastershopClient, MastershopTransport
from app.integrations.mastershop.payload import MastershopPayloadError, build_order_payload
from app.services.platform_config import FulfillmentConfig


class MastershopSyncService:
    """Attempt one handoff while preserving the committed local order."""

    def __init__(
        self,
        db: Prisma,
        config: FulfillmentConfig,
        transport: MastershopTransport | None = None,
    ) -> None:
        self._db = db
        self._config = config
        self._transport = transport

    async def sync_order(self, order_id: int) -> Any:
        order = await self._db.order.find_unique(
            where={"id": order_id},
            include={
                "product": True,
                "fulfillmentDetails": True,
                "mastershopSync": True,
            },
        )
        if order is None:
            raise ValueError("Order not found")
        sync = order.mastershopSync
        if sync is None:
            raise ValueError("This historical order has no MasterShop synchronization record")
        if sync.status == "success":
            return sync
        if order.status != "pending":
            return await self._db.mastershopordersync.update(
                where={"orderId": order.id}, data={"status": "waiting_review"}
            )
        # A worker can die after claiming a row but before recording a result.
        # Recent claims are left alone. An Administrator may reclaim an old
        # claim after reconciling the stable `bp_<local order id>` in
        # MasterShop; the provider's public material does not promise an
        # idempotency-key header.
        stale_before = datetime.now(UTC) - timedelta(
            seconds=max(60.0, (self._config.mastershop_timeout_seconds * 2) + 10)
        )

        claimed = await self._db.mastershopordersync.update_many(
            where={
                "orderId": order.id,
                "OR": [
                    {"status": {"in": ["pending", "failed", "waiting_review"]}},
                    {
                        "status": "syncing",
                        "OR": [
                            {"lastAttemptAt": None},
                            {"lastAttemptAt": {"lte": stale_before}},
                        ],
                    },
                ],
            },
            data={
                "status": "syncing",
                "attemptCount": {"increment": 1},
                "lastAttemptAt": datetime.now(UTC),
            },
        )
        if claimed == 0:
            return await self._db.mastershopordersync.find_unique(where={"orderId": order.id})

        # Reload only after winning the claim. Admin edits take the same row
        # lock through a conditional status update, so this is the canonical
        # snapshot for the outbound request.
        order = await self._db.order.find_unique(
            where={"id": order_id},
            include={
                "product": True,
                "fulfillmentDetails": True,
                "mastershopSync": True,
            },
        )
        if order is None:
            raise ValueError("Order not found")
        if order.status != "pending":
            return await self._db.mastershopordersync.update(
                where={"orderId": order.id}, data={"status": "waiting_review"}
            )
        if order.fulfillmentDetails is None:
            return await self._fail(order.id, "Structured fulfillment details are missing.")

        mappings = await self._db.mastershopproductmapping.find_many(
            where={"productId": order.productId}
        )
        try:
            payload = build_order_payload(
                order=order,
                details=order.fulfillmentDetails,
                mappings=mappings,
            )
        except MastershopPayloadError as exc:
            return await self._fail(order.id, str(exc))

        await self._db.mastershopordersync.update(
            where={"orderId": order.id}, data={"requestBody": Json(payload)}
        )
        api_key = self._config.mastershop_api_key.strip()
        if not api_key:
            return await self._fail(order.id, "The MasterShop API key is not configured.")
        orders_url = self._config.mastershop_orders_url.strip()
        if not orders_url:
            return await self._fail(order.id, "The MasterShop orders URL is not configured.")

        transport = self._transport or MastershopClient(
            api_key=api_key,
            orders_url=orders_url,
            timeout_seconds=self._config.mastershop_timeout_seconds,
        )
        try:
            response = await transport.create_order(payload)
        except httpx.TimeoutException:
            return await self._fail(order.id, "MasterShop request timed out.")
        except httpx.HTTPError:
            return await self._fail(order.id, "MasterShop request failed before a response.")
        except Exception:
            # The public order is already committed. Never leak transport
            # internals or turn a provider/client bug into a failed checkout.
            return await self._fail(order.id, "Unexpected MasterShop synchronization failure.")

        if response.status_code != 200:
            return await self._fail(
                order.id,
                f"MasterShop returned HTTP {response.status_code}.",
                response_status=response.status_code,
                response_body=response.body,
            )
        return await self._db.mastershopordersync.update(
            where={"orderId": order.id},
            data={
                "status": "success",
                "responseStatus": response.status_code,
                "responseBody": Json(response.body),
                "lastError": None,
                "syncedAt": datetime.now(UTC),
            },
        )

    async def _fail(
        self,
        order_id: int,
        message: str,
        *,
        response_status: int | None = None,
        response_body: Any | None = None,
    ) -> Any:
        return await self._db.mastershopordersync.update(
            where={"orderId": order_id},
            data={
                "status": "failed",
                "responseStatus": response_status,
                # prisma-client-py requires its Json wrapper for nullable JSON
                # writes; plain None is interpreted as a missing input value.
                "responseBody": Json(response_body),
                "lastError": message[:1000],
                "syncedAt": None,
            },
        )
