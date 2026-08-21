from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from app.integrations.mastershop.client import MastershopClient, MastershopHttpResult
from app.integrations.mastershop.payload import MastershopPayloadError, build_order_payload
from app.integrations.mastershop.service import MastershopSyncService


def _order(*, selections=None, quantity: int = 1):
    return SimpleNamespace(
        id=9,
        quantity=quantity,
        variantSelections=selections or [],
        totalPrice=Decimal("59900"),
        phoneNormalizedKey="3222615532",
        phoneE164="+573222615532",
        department="ANTIOQUIA",
        city="MEDELLÍN",
        product=SimpleNamespace(sku="24", name="Jogger"),
    )


def _details():
    return SimpleNamespace(
        firstName="Cesar",
        lastName="Pulido",
        address1="Calle 10 #01-12",
        address2=None,
    )


def _mapping(*, selection=None, variant_id=None):
    from app.integrations.mastershop.payload import selection_key

    selection = selection or {}
    return SimpleNamespace(
        selectionKey=selection_key(selection),
        mastershopProductId=232082,
        mastershopVariantId=variant_id,
        weight=Decimal("1"),
    )


def test_builds_the_documented_mastershop_payload() -> None:
    payload = build_order_payload(order=_order(), details=_details(), mappings=[_mapping()])

    assert payload["id_order"] == "bp_9"
    assert payload["shipping_address"] == {
        "country": "CO",
        "state": "Antioquia",
        "city": "Medellín",
        "address1": "Calle 10 #01-12",
        "address2": None,
        "company": None,
        "zip": None,
        "full_name": "Cesar Pulido",
        "first_name": "Cesar",
        "last_name": "Pulido",
        "phone": "573222615532",
    }
    assert payload["customer"]["phone"] == "3222615532"
    assert payload["order_transaction"]["total"] == 59900
    assert payload["order_items"] == [
        {
            "id_variant": None,
            "id_product": 232082,
            "quantity": 1,
            "sku": "24",
            "name": "Jogger",
            "weight": 1,
            "price": 59900,
        }
    ]


def test_groups_equal_variants_and_requires_every_mapping() -> None:
    gray = {"Color": "Gris"}
    payload = build_order_payload(
        order=_order(selections=[gray, gray], quantity=2),
        details=_details(),
        mappings=[_mapping(selection=gray, variant_id=456)],
    )
    assert payload["order_items"][0]["id_variant"] == 456
    assert payload["order_items"][0]["quantity"] == 2

    with pytest.raises(MastershopPayloadError, match="Missing MasterShop mapping"):
        build_order_payload(order=_order(), details=_details(), mappings=[])


@pytest.mark.asyncio
async def test_client_uses_ms_api_key_and_preserves_non_200_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["ms-api-key"] == "secret"
        assert request.url == "https://prod.api.mastershop.com/api/orders"
        return httpx.Response(422, json={"message": "invalid variant"})

    client = MastershopClient(
        api_key="secret",
        orders_url="https://prod.api.mastershop.com/api/orders",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    result = await client.create_order({"id_order": "bp_9"})

    assert result.status_code == 422
    assert result.body == {"message": "invalid variant"}


class _OrderActions:
    def __init__(self, order) -> None:
        self.order = order

    async def find_unique(self, **_kwargs):
        return self.order


class _MappingActions:
    def __init__(self, mapping) -> None:
        self.mapping = mapping

    async def find_many(self, **_kwargs):
        return [self.mapping]


class _SyncActions:
    def __init__(self, sync) -> None:
        self.sync = sync
        self.updates: list[dict] = []

    async def update_many(self, **kwargs):
        self.updates.append(kwargs["data"])
        self.sync.status = "syncing"
        self.sync.attemptCount += 1
        return 1

    async def update(self, **kwargs):
        data = kwargs["data"]
        self.updates.append(data)
        for key, value in data.items():
            setattr(self.sync, key, value)
        return self.sync

    async def find_unique(self, **_kwargs):
        return self.sync


class _Db:
    def __init__(self) -> None:
        sync = SimpleNamespace(
            status="pending",
            attemptCount=0,
            lastAttemptAt=None,
        )
        order = _order()
        order.productId = 12
        order.status = "pending"
        order.fulfillmentDetails = _details()
        order.mastershopSync = sync
        self.order = _OrderActions(order)
        self.mastershopproductmapping = _MappingActions(_mapping())
        self.mastershopordersync = _SyncActions(sync)


class _RejectedTransport:
    async def create_order(self, _payload):
        return MastershopHttpResult(422, {"message": "invalid variant"})


@pytest.mark.asyncio
async def test_service_durably_records_non_200_without_touching_local_order() -> None:
    db = _Db()
    settings = SimpleNamespace(
        mastershop_api_key="secret",
        mastershop_orders_url="https://prod.api.mastershop.com/api/orders",
        mastershop_timeout_seconds=5,
    )

    result = await MastershopSyncService(  # type: ignore[arg-type]
        db,
        settings,
        _RejectedTransport(),  # type: ignore[arg-type]
    ).sync_order(9)

    assert result.status == "failed"
    assert result.attemptCount == 1
    assert result.responseStatus == 422
    assert result.responseBody.data == {"message": "invalid variant"}
    assert result.lastError == "MasterShop returned HTTP 422."
