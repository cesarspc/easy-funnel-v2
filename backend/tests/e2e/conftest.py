"""Fixtures for the end-to-end COD flow tests.

These tests drive the real FastAPI application over ASGI against a real
PostgreSQL database (docs/testing.md -> Integration Tests), so the critical
path is exercised end to end: publish active product -> open landing ->
click CTA -> submit COD form -> fraud evaluation -> order + flags readable
by the admin data layer.

Two collaborators are injected as test doubles through FastAPI's
`dependency_overrides`, because neither can be reached from a test run:

- **Redis** — the docker `redis` container speaks the Redis wire protocol
  while the application client speaks the Upstash REST API, so the
  in-process double from `tests/redis/fakes.py` stands in (the same double
  the `tests/redis/` unit tests use). It gives each test a clean
  rolling-window counter, which is what makes rate-limit assertions
  deterministic.
- **GeoIP** — the MaxMind GeoLite2 database is a licensed binary that is not
  committed to the repository, so `StubGeoIpResolver` returns a fixed
  resolution. Tests that do not care about GeoIP get the same
  `unavailable` result the real resolver produces without the database.

Everything else (Prisma, fraud evaluation, persistence, audit) is real.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal

import pytest_asyncio
from app.core.jwt_auth import issue_token
from app.core.password_hashing import hash_password
from app.core.settings import get_settings
from app.db.client import connect_db, disconnect_db, get_db
from app.main import app
from app.redis.client import get_redis
from app.services.geoip_resolver import get_geoip_resolver
from app.storage.dependencies import get_r2_client
from httpx import ASGITransport, AsyncClient
from prisma import Prisma

from tests.redis.fakes import FakeRedis
from tests.storage.fakes import FakeR2Client


@dataclass(frozen=True)
class SeededLanding:
    """A product + landing pair created for one test."""

    product_id: int
    landing_id: int
    slug: str


@dataclass(frozen=True)
class SeededBanner:
    """A banner/image asset pair created for one test."""

    banner_id: int
    image_asset_id: int
    opaque_key: str


class StubGeoIpResolver:
    """GeoIP resolver double returning a fixed (country, region, status)."""

    def __init__(
        self,
        *,
        country: str | None = None,
        region: str | None = None,
        status: str = "unavailable",
    ) -> None:
        self.country = country
        self.region = region
        self.status = status

    def resolve(self, ip_address: str) -> tuple[str | None, str | None, str]:
        del ip_address
        return self.country, self.region, self.status


class CodFlowHarness:
    """Seeds catalog rows for one test and cleans up everything it created."""

    def __init__(self, client: AsyncClient, db: Prisma, redis: FakeRedis, r2: FakeR2Client) -> None:
        self.client = client
        self.db = db
        self.redis = redis
        self.r2 = r2
        self.geoip = StubGeoIpResolver()
        self._landings: list[SeededLanding] = []
        self._blacklist_ids: list[int] = []
        self._geoip_rule_ids: list[int] = []
        self._admin_usernames: list[str] = []
        # `landing_templates` has no FK to a landing (a template outlives the
        # landing it was saved from, by design), so nothing else would clean
        # these up and they would leak between tests.
        self._template_ids: list[int] = []

    async def seed_landing(
        self,
        *,
        product_status: str = "active",
        landing_status: str = "published",
        cta_band_style: str = "gradient",
    ) -> SeededLanding:
        """Create a product + landing in the requested lifecycle states."""
        suffix = uuid.uuid4().hex[:12]
        product = await self.db.product.create(
            {
                "name": f"E2E Product {suffix}",
                "sku": f"E2E-{suffix}",
                "price": Decimal("59900.00"),
                "status": product_status,
            }
        )
        landing = await self.db.landing.create(
            {
                "productId": product.id,
                "slug": f"e2e-{suffix}",
                "status": landing_status,
                "ctaMode": "after_every",
                "ctaPositions": [],
                "formPresentation": "inline",
                "ctaBandStyle": cta_band_style,
            }
        )
        seeded = SeededLanding(product_id=product.id, landing_id=landing.id, slug=landing.slug)
        self._landings.append(seeded)
        return seeded

    async def seed_banner(
        self,
        landing: SeededLanding,
        *,
        order_index: int = 0,
        with_variants: bool = True,
        top_edge_color: str | None = None,
        bottom_edge_color: str | None = None,
        edges_flat: bool = True,
    ) -> SeededBanner:
        """Attach a complete image asset and optional variants to a landing.

        `with_variants=False` models a legacy/malformed asset so the public
        serializer's defensive behavior is covered independently from the
        normal upload pipeline tests.

        Edge colors default to unset, which models an asset created before
        edge extraction existed. `edges_flat=False` models the common real
        case — a photographic edge whose color was extracted but whose strip
        is too busy for the flatness test — which must still paint.
        """
        suffix = uuid.uuid4().hex[:12]
        opaque_key = f"e2e-image-{suffix}"
        asset = await self.db.imageasset.create(
            {
                "opaqueKey": opaque_key,
                "sourceObjectKey": f"originals/{opaque_key}.jpg",
                "sourceWidth": 1200,
                "sourceHeight": 800,
                "sourceFormat": "jpeg",
                "status": "complete",
                "topEdgeColor": top_edge_color,
                "bottomEdgeColor": bottom_edge_color,
                "topEdgeFlat": edges_flat and top_edge_color is not None,
                "bottomEdgeFlat": edges_flat and bottom_edge_color is not None,
            }
        )
        if with_variants:
            await self.db.imagevariant.create(
                {
                    "imageAssetId": asset.id,
                    "width": 480,
                    "height": 320,
                    "format": "jpeg",
                    "objectKey": f"variants/{opaque_key}/480.jpg",
                    "version": opaque_key,
                }
            )
            await self.db.imagevariant.create(
                {
                    "imageAssetId": asset.id,
                    "width": 800,
                    "height": 533,
                    "format": "webp",
                    "objectKey": f"variants/{opaque_key}/800.webp",
                    "version": opaque_key,
                }
            )
        banner = await self.db.banner.create(
            {
                "landingId": landing.landing_id,
                "orderIndex": order_index,
                "altText": f"E2E banner {order_index}",
                "imageAssetId": asset.id,
            }
        )
        return SeededBanner(
            banner_id=banner.id,
            image_asset_id=asset.id,
            opaque_key=opaque_key,
        )

    async def blacklist_phone(self, phone_normalized_key: str, *, reason: str) -> None:
        """Add a phone entry to the manual blacklist for this test."""
        entry = await self.db.blacklistentry.create(
            {
                "entryType": "phone",
                "valueNormalized": phone_normalized_key,
                "reason": reason,
            }
        )
        self._blacklist_ids.append(entry.id)

    async def add_geoip_rule(self, location_code: str, *, action: str) -> None:
        """Enable a GeoIP rule for this test."""
        rule = await self.db.geoiprule.create(
            {"locationCode": location_code, "action": action, "enabled": True}
        )
        self._geoip_rule_ids.append(rule.id)

    async def seed_admin(self, *, password: str = "correct-password") -> tuple[str, str]:
        """Create a uniquely named Administrator and return its credentials."""
        username = f"e2e-admin-{uuid.uuid4().hex[:12]}"
        await self.db.adminuser.create(
            {
                "username": username,
                "passwordHash": hash_password(password),
                "role": "admin",
            }
        )
        self._admin_usernames.append(username)
        return username, password

    def track_template(self, template_id: int) -> int:
        """Register a template created through the API for cleanup.

        Templates are saved by the endpoint under test rather than seeded here,
        so the test hands the id back for teardown.
        """
        self._template_ids.append(template_id)
        return template_id

    def admin_headers(self, subject: str = "e2e-admin") -> dict[str, str]:
        """Authorization header for the admin endpoints.

        Issues a real session token with the application's own signing helper
        and sends it over the bearer transport `require_admin` supports for
        non-browser clients, so the admin steps exercise the real
        authorization dependency.
        """
        token = issue_token(get_settings(), subject=subject)
        return {"Authorization": f"Bearer {token}"}

    def resolve_geoip_as(self, country: str, *, region: str | None = None) -> None:
        """Make the injected resolver report `country` for every request IP."""
        self.geoip.country = country
        self.geoip.region = region
        self.geoip.status = "resolved"

    async def orders_for(self, landing: SeededLanding) -> list:
        """Return the landing's orders with fraud flags, oldest first.

        Reads through the same include the admin order detail uses, so the
        assertions cover what an Administrator would see.
        """
        return await self.db.order.find_many(
            where={"landingId": landing.landing_id},
            include={
                "fraudFlags": True,
                "fulfillmentDetails": True,
                "mastershopSync": True,
            },
            order={"id": "asc"},
        )

    async def cleanup(self) -> None:
        """Delete every row this harness created, children first."""
        for template_id in self._template_ids:
            await self.db.auditlog.delete_many(
                where={"targetType": "landing_template", "targetId": str(template_id)}
            )
            await self.db.landingtemplate.delete_many(where={"id": template_id})
        for username in self._admin_usernames:
            await self.db.auditlog.delete_many(where={"actor": username})
            await self.db.adminuser.delete(where={"username": username})
        for rule_id in self._geoip_rule_ids:
            await self.db.geoiprule.delete(where={"id": rule_id})
        for entry_id in self._blacklist_ids:
            await self.db.blacklistentry.delete(where={"id": entry_id})
        for landing in self._landings:
            orders = await self.db.order.find_many(where={"landingId": landing.landing_id})
            for order in orders:
                await self.db.fraudflag.delete_many(where={"orderId": order.id})
                await self.db.mastershopordersync.delete_many(where={"orderId": order.id})
                await self.db.orderfulfillmentdetails.delete_many(where={"orderId": order.id})
            await self.db.order.delete_many(where={"landingId": landing.landing_id})
            await self.db.execute_raw(
                'DELETE FROM "landing_analytics_daily" WHERE "landing_id" = $1',
                landing.landing_id,
            )
            await self.db.ctaclick.delete_many(where={"landingId": landing.landing_id})
            await self.db.landingview.delete_many(where={"landingId": landing.landing_id})
            stored_banners = await self.db.banner.find_many(where={"landingId": landing.landing_id})
            image_asset_ids = [banner.imageAssetId for banner in stored_banners]
            for banner in stored_banners:
                await self.db.auditlog.delete_many(
                    where={"targetType": "banner", "targetId": str(banner.id)}
                )
            await self.db.auditlog.delete_many(
                where={"targetType": "landing", "targetId": str(landing.landing_id)}
            )
            # `landing_blocks` holds a restrict FK to the landing, so placed
            # components (and their audit rows) go before the landing itself.
            stored_blocks = await self.db.landingblock.find_many(
                where={"landingId": landing.landing_id}
            )
            for block in stored_blocks:
                await self.db.auditlog.delete_many(
                    where={"targetType": "landing_block", "targetId": str(block.id)}
                )
            await self.db.landingblock.delete_many(where={"landingId": landing.landing_id})
            await self.db.banner.delete_many(where={"landingId": landing.landing_id})
            for image_asset_id in image_asset_ids:
                await self.db.imagevariant.delete_many(where={"imageAssetId": image_asset_id})
                await self.db.imageasset.delete(where={"id": image_asset_id})
            await self.db.landing.delete(where={"id": landing.landing_id})
            await self.db.mastershopproductmapping.delete_many(
                where={"productId": landing.product_id}
            )
            await self.db.product.delete(where={"id": landing.product_id})


@pytest_asyncio.fixture
async def cod_flow() -> AsyncIterator[CodFlowHarness]:
    """Yield a harness wired to the real app over ASGI."""
    await connect_db()
    db = get_db()
    redis = FakeRedis()
    r2 = FakeR2Client()
    harness = CodFlowHarness(client=None, db=db, redis=redis, r2=r2)  # type: ignore[arg-type]

    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_geoip_resolver] = lambda: harness.geoip
    # R2 is not reachable from a test run, so the admin banner-upload endpoint
    # writes into the same in-process double the image pipeline unit tests use.
    app.dependency_overrides[get_r2_client] = lambda: r2

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            harness.client = client
            yield harness
    finally:
        app.dependency_overrides.pop(get_redis, None)
        app.dependency_overrides.pop(get_geoip_resolver, None)
        app.dependency_overrides.pop(get_r2_client, None)
        await harness.cleanup()
        await disconnect_db()


def unique_phone() -> str:
    """Return a synthetic Colombian mobile number unique to this call.

    Uniqueness keeps duplicate/blacklist state from leaking between tests and
    between runs against a database that is not reset.
    """
    return f"3{uuid.uuid4().int % 10**9:09d}"
