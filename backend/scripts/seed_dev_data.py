"""Seed a browsable development dataset: products, landings, banners, orders.

The backend test suite is not a data source — `backend/tests/db/` runs
`prisma migrate reset` and the e2e tests clean up after themselves, so a
finished test run leaves an empty database (docs/testing.md -> Database).
This script fills that gap for local exploration of the admin dashboard and
the public landing: catalog rows, real banner images in the local
S3-compatible bucket, view/click analytics, and orders in every fraud state
the Core Flow can produce.

Everything goes through the real ASGI application (authenticated admin API +
public API), so seeded rows obey the same validation, fraud evaluation, and
audit rules a merchant would hit. Nothing is inserted behind the services.

One collaborator is injected as an in-process double: the licensed MaxMind
GeoLite2 database is not committed, so `SeedGeoIpResolver` stands in for it.
Every other collaborator — Prisma, Redis, R2/MinIO, fraud evaluation, audit —
is the real one, so seeded analytics and rate-limit counters end up in the same
state a real day of traffic would produce.

Redis used to be doubled here too, back when the application client spoke the
Upstash REST API and could not reach the local container. It speaks the normal
Redis protocol now (`app/redis/client.py`), and that stub was never taught
about the second Lua script `LandingTrafficService` added, so it returned a
bare count where a `{count, has_older_day}` pair was expected and seeding a
landing view crashed. Using the real client removes the whole class of drift.

Refuses to run unless `ENVIRONMENT` is `development`, and it is idempotent by
truncation: it removes previously seeded catalog/order rows before recreating
them, so repeated runs do not accumulate SKU conflicts.

Usage (PowerShell), with the docker-compose services and MinIO running:

    $env:ADMIN_PASSWORD = "..."
    python -m scripts.seed_dev_data --username admin

Requires an Administrator account (create one with `scripts.seed_admin`).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.core.settings import get_settings
from app.domains.orders.locations import location_catalog
from app.db.client import connect_db, disconnect_db, get_db
from app.main import app
from app.services.geoip_resolver import get_geoip_resolver
from httpx import ASGITransport, AsyncClient
from PIL import Image, ImageDraw

BANNER_SIZE = (1200, 1500)


class SeedGeoIpResolver:
    """GeoIP resolver double: the same `unavailable` result the real resolver
    returns when the licensed GeoLite2 database is not present."""

    def resolve(self, ip_address: str) -> tuple[str | None, str | None, str]:  # noqa: ARG002
        return None, None, "unavailable"


@dataclass(frozen=True)
class BannerSpec:
    top: tuple[int, int, int]
    bottom: tuple[int, int, int]
    label: str
    alt_text: str


@dataclass(frozen=True)
class CatalogSpec:
    name: str
    sku: str
    price: float
    description: str
    slug: str
    cta_mode: str
    cta_interval: int | None
    cta_positions: list[int] | None
    form_presentation: str
    cta_band_style: str
    banners: tuple[BannerSpec, ...]
    # Conversion components: (block_type, slot_index, config). Slot indexes
    # count rendered elements (banners + CTA bands), so slot 1 sits between the
    # first banner and whatever follows it.
    blocks: tuple[tuple[str, int, dict[str, Any]], ...] = ()


CATALOG: tuple[CatalogSpec, ...] = (
    CatalogSpec(
        name="Set de Sartenes Antiadherentes",
        sku="DEV-SARTEN-3P",
        price=89900.0,
        description=(
            "Juego de 3 sartenes con recubrimiento antiadherente, aptas para "
            "todo tipo de estufa. Datos sinteticos de desarrollo."
        ),
        slug="set-sartenes-dev",
        cta_mode="after_every",
        cta_interval=None,
        cta_positions=None,
        form_presentation="inline",
        cta_band_style="gradient",
        banners=(
            BannerSpec((250, 240, 232), (238, 226, 214), "1", "Set de 3 sartenes sobre mesa"),
            BannerSpec((238, 226, 214), (214, 198, 184), "2", "Detalle del recubrimiento"),
            BannerSpec((214, 198, 184), (196, 176, 160), "3", "Sarten en uso en la estufa"),
        ),
        blocks=(
            ("cod_assurance", 1, {"note": "Cobertura en las principales ciudades del pais."}),
            (
                "benefits",
                2,
                {
                    "title": "Por que este juego",
                    "items": [
                        "Recubrimiento antiadherente en las tres piezas",
                        "Sirve en estufa de gas y electrica",
                        "Se lava facil, sin esponja de metal",
                    ],
                },
            ),
            ("offer_price", 4, {"compare_at_price": 129900, "note": "Precio de lanzamiento."}),
            (
                "faq",
                6,
                {
                    "items": [
                        {
                            "question": "Cuanto tarda la entrega?",
                            "answer": "Entre 1 y 3 dias habiles segun la ciudad.",
                        },
                        {
                            "question": "Como pago?",
                            "answer": "En efectivo al mensajero, cuando recibes el pedido.",
                        },
                    ]
                },
            ),
        ),
    ),
    CatalogSpec(
        name="Reloj Deportivo Resistente al Agua",
        sku="DEV-RELOJ-SPT",
        price=64900.0,
        description=(
            "Reloj deportivo con correa de silicona y resistencia al agua. "
            "Datos sinteticos de desarrollo."
        ),
        slug="reloj-deportivo-dev",
        cta_mode="every_n",
        cta_interval=2,
        cta_positions=None,
        form_presentation="modal",
        cta_band_style="solid",
        banners=(
            BannerSpec((18, 24, 38), (28, 38, 58), "1", "Reloj deportivo negro de frente"),
            BannerSpec((28, 38, 58), (44, 58, 82), "2", "Correa de silicona en detalle"),
            BannerSpec((44, 58, 82), (66, 84, 112), "3", "Reloj bajo gotas de agua"),
            BannerSpec((66, 84, 112), (96, 116, 148), "4", "Reloj en la muneca"),
        ),
        blocks=(
            (
                "included_benefits",
                1,
                {
                    "items": [
                        {"name": "Reloj deportivo resistente al agua", "value": "Valor $64.900", "tag": ""},
                        {"name": "Correa de silicona extra", "value": "Valor $19.900", "tag": "GRATIS"},
                        {"name": "Estuche de transporte", "value": "Valor $12.000", "tag": "GRATIS"},
                    ]
                },
            ),
            (
                "guarantee",
                3,
                {
                    "title": "Garantia de la correa",
                    "text": "Si la correa se rompe en el primer mes, la reponemos.",
                    "days": 30,
                },
            ),
        ),
    ),
    CatalogSpec(
        name="Organizador Plegable de Closet",
        sku="DEV-ORGZ-CLST",
        price=39900.0,
        description=(
            "Organizador plegable de tela con 6 compartimentos. Datos sinteticos de desarrollo."
        ),
        slug="organizador-closet-dev",
        cta_mode="fixed_positions",
        cta_interval=None,
        cta_positions=[1, 3],
        form_presentation="inline",
        cta_band_style="gradient",
        banners=(
            BannerSpec((236, 244, 240), (208, 228, 220), "1", "Organizador armado en el closet"),
            BannerSpec((208, 228, 220), (176, 206, 196), "2", "Compartimentos con ropa doblada"),
            BannerSpec((176, 206, 196), (146, 184, 172), "3", "Organizador plegado en la mano"),
        ),
    ),
)

def _canonical_location(department: str, city: str) -> tuple[str, str]:
    """Map a readable fixture place name onto its exact catalog spelling.

    The delivery catalog is DIVIPOLA data: upper case and accented
    ("ANTIOQUIA" / "MEDELLIN" with an accent), and validation compares the
    names as written. These fixtures were authored before that catalog landed
    and still spell places the way a person would, so every seeded order was
    rejected with "Select a city or municipality belonging to the chosen
    department". Matching accent-insensitively here keeps the fixtures readable
    and lets the catalog stay the single source of truth.
    """

    def fold(value: str) -> str:
        decomposed = unicodedata.normalize("NFD", value)
        return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").upper()

    catalog = location_catalog()
    target_department, target_city = fold(department), fold(city)
    for entry in catalog["departments"]:
        if fold(entry["name"]) != target_department:
            continue
        for municipality in entry["cities"]:
            if fold(municipality["name"]) == target_city:
                return entry["name"], municipality["name"]
        raise RuntimeError(f"{city!r} is not a municipality of {department!r} in the catalog.")
    raise RuntimeError(f"{department!r} is not a department in the catalog.")


# Synthetic Colombian order data. Phones stay inside the documented test
# examples' shape (docs/testing.md -> Test Data) and are not real numbers.
ORDERS: tuple[dict[str, Any], ...] = (
    {
        "slug": "set-sartenes-dev",
        "full_name": "Camila Restrepo",
        "phone": "300 123 4567",
        "department": "Antioquia",
        "city": "Medellin",
        "address": "Calle 10 # 43-25 Apto 302",
        "quantity": 1,
        "ip": "190.85.10.11",
        "note": "clean order -> pending",
    },
    {
        "slug": "set-sartenes-dev",
        "full_name": "Andres Gomez",
        "phone": "301-222-3344",
        "department": "Bogota D.C.",
        "city": "Bogota D.C.",
        "address": "Carrera 7 # 122-15 Torre 2",
        "quantity": 2,
        "ip": "190.85.10.12",
        "note": "clean order -> pending",
    },
    {
        "slug": "reloj-deportivo-dev",
        "full_name": "Laura Vargas",
        "phone": "(302) 555 8899",
        "department": "Valle del Cauca",
        "city": "Cali",
        "address": "Avenida 6N # 28-40",
        "quantity": 1,
        "ip": "190.85.10.13",
        "note": "clean order -> pending",
    },
    {
        "slug": "reloj-deportivo-dev",
        "full_name": "Laura Vargas",
        "phone": "(302) 555 8899",
        "department": "Valle del Cauca",
        "city": "Cali",
        "address": "Avenida 6N # 28-40",
        "quantity": 1,
        "ip": "190.85.10.13",
        "note": "same phone + ip inside the window -> duplicate flag",
    },
    {
        "slug": "organizador-closet-dev",
        "full_name": "Sofia Herrera",
        "phone": "57 303 777 1122",
        "department": "Atlantico",
        "city": "Barranquilla",
        "address": "Calle 84 # 51-30",
        "quantity": 3,
        "ip": "190.85.10.14",
        "note": "blacklisted phone -> blacklist flag",
    },
    {
        "slug": "organizador-closet-dev",
        "full_name": "Julian Mesa",
        "phone": "304 909 0909",
        "department": "Santander",
        "city": "Bucaramanga",
        "address": "Carrera 27 # 36-12",
        "quantity": 1,
        "ip": "45.230.99.99",
        "note": "blacklisted ip -> blacklist flag",
    },
)

BLACKLIST: tuple[dict[str, str], ...] = (
    {
        "entry_type": "phone",
        "value_normalized": "+573037771122",
        "reason": "Development sample: repeated refused deliveries.",
    },
    {
        "entry_type": "ip",
        "value_normalized": "45.230.99.99",
        "reason": "Development sample: automated submissions from this address.",
    },
)


def _banner_bytes(spec: BannerSpec) -> bytes:
    """Render a vertical two-color gradient banner with a position label.

    Flat top and bottom edge strips are what make the seeded CTA bands
    meaningful: `extract_edge_colors` samples them at upload time.
    """
    width, height = BANNER_SIZE
    image = Image.new("RGB", (width, height), spec.top)
    draw = ImageDraw.Draw(image)

    edge_strip = height // 12
    for y in range(height):
        if y < edge_strip:
            color = spec.top
        elif y >= height - edge_strip:
            color = spec.bottom
        else:
            ratio = (y - edge_strip) / max(height - 2 * edge_strip - 1, 1)
            color = tuple(
                round(spec.top[channel] + (spec.bottom[channel] - spec.top[channel]) * ratio)
                for channel in range(3)
            )
        draw.line([(0, y), (width, y)], fill=color)

    mid = tuple(255 - channel for channel in spec.top)
    draw.text((width // 2 - 8, height // 2 - 8), spec.label, fill=mid)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


async def _reset_seeded_rows() -> None:
    """Delete rows this script owns, oldest dependency last.

    Orders and fraud flags use restrict FKs, so they must go before the
    landings and products they reference.
    """
    db = get_db()
    # Everything that points at an order goes first. All three of these hold
    # restrict FKs (design.md: historical evidence never cascades), so deleting
    # an order out from under any one of them fails. Only `fraud_flags` was
    # cleared here originally, which is why the first seed of an empty database
    # succeeded and every re-seed afterwards died on
    # `order_fulfillment_details_order_id_fkey`: the order pipeline writes a
    # fulfillment row for *every* order it accepts.
    await db.execute_raw(
        """
        DELETE FROM fraud_flags
         WHERE order_id IN (SELECT id FROM orders WHERE landing_slug LIKE '%-dev')
        """
    )
    await db.execute_raw(
        """
        DELETE FROM order_fulfillment_details
         WHERE order_id IN (SELECT id FROM orders WHERE landing_slug LIKE '%-dev')
        """
    )
    # Empty unless FULFILLMENT_PROVIDER=mastershop, but a re-seed on a stack
    # that has it enabled would hit the same wall.
    await db.execute_raw(
        """
        DELETE FROM mastershop_order_syncs
         WHERE order_id IN (SELECT id FROM orders WHERE landing_slug LIKE '%-dev')
        """
    )
    await db.execute_raw("DELETE FROM orders WHERE landing_slug LIKE '%-dev'")
    await db.execute_raw(
        """
        DELETE FROM landing_views
         WHERE landing_id IN (SELECT id FROM landings WHERE slug LIKE '%-dev')
        """
    )
    await db.execute_raw(
        """
        DELETE FROM cta_clicks
         WHERE landing_id IN (SELECT id FROM landings WHERE slug LIKE '%-dev')
        """
    )
    await db.execute_raw(
        """
        DELETE FROM banners
         WHERE landing_id IN (SELECT id FROM landings WHERE slug LIKE '%-dev')
        """
    )
    # Conversion components hold a restrict FK to the landing, so they go before
    # the landings they were placed on.
    await db.execute_raw(
        """
        DELETE FROM landing_blocks
         WHERE landing_id IN (SELECT id FROM landings WHERE slug LIKE '%-dev')
        """
    )
    await db.execute_raw(
        """
        DELETE FROM landings
         WHERE product_id IN (SELECT id FROM products WHERE sku LIKE 'DEV-%')
        """
    )
    await db.execute_raw("DELETE FROM products WHERE sku LIKE 'DEV-%'")
    # Banner deletion orphans the image assets and variants those banners
    # pointed at; without this the variant count grows on every re-seed.
    await db.execute_raw(
        """
        DELETE FROM image_variants
         WHERE image_asset_id NOT IN (SELECT image_asset_id FROM banners)
        """
    )
    await db.execute_raw(
        "DELETE FROM image_assets WHERE id NOT IN (SELECT image_asset_id FROM banners)"
    )
    await db.execute_raw("DELETE FROM blacklist_entries WHERE reason LIKE 'Development sample:%'")


def _fail(response: Any, what: str) -> None:
    raise RuntimeError(f"{what} failed: HTTP {response.status_code} {response.text}")


async def seed(*, username: str, password: str) -> dict[str, int]:
    settings = get_settings()
    if settings.environment != "development":
        raise RuntimeError(
            f"Refusing to run: ENVIRONMENT is {settings.environment!r}, not 'development'."
        )

    await connect_db()
    db = get_db()
    seed_geoip = SeedGeoIpResolver()
    app.dependency_overrides[get_geoip_resolver] = lambda: seed_geoip
    try:
        await _reset_seeded_rows()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://seed.local") as client:
            login = await client.post(
                "/api/auth/login", json={"username": username, "password": password}
            )
            if login.status_code != 200:
                _fail(login, "Admin login")

            for entry in BLACKLIST:
                created = await client.post("/api/admin/fraud/blacklist", json=entry)
                if created.status_code not in (201, 409):
                    _fail(created, f"Blacklist entry {entry['value_normalized']}")

            for spec in CATALOG:
                product = await client.post(
                    "/api/admin/products",
                    json={
                        "name": spec.name,
                        "sku": spec.sku,
                        "price": spec.price,
                        "description": spec.description,
                    },
                )
                if product.status_code != 201:
                    _fail(product, f"Product {spec.sku}")
                product_id = product.json()["id"]

                landing = await db.landing.find_unique(where={"productId": product_id})
                if landing is None:
                    raise RuntimeError(f"Product {spec.sku} was created without a draft landing.")
                landing_id = landing.id

                config: dict[str, Any] = {
                    "slug": spec.slug,
                    "cta_mode": spec.cta_mode,
                    "form_presentation": spec.form_presentation,
                    "cta_band_style": spec.cta_band_style,
                }
                if spec.cta_interval is not None:
                    config["cta_interval"] = spec.cta_interval
                if spec.cta_positions is not None:
                    config["cta_positions"] = spec.cta_positions

                configured = await client.patch(f"/api/admin/landings/{landing_id}", json=config)
                if configured.status_code != 200:
                    _fail(configured, f"Landing config {spec.slug}")

                for banner in spec.banners:
                    uploaded = await client.post(
                        f"/api/admin/landings/{landing_id}/banners",
                        files={
                            "file": (
                                f"{spec.sku}-{banner.label}.jpg",
                                _banner_bytes(banner),
                                "image/jpeg",
                            )
                        },
                        data={"alt_text": banner.alt_text},
                    )
                    if uploaded.status_code != 201:
                        _fail(uploaded, f"Banner upload for {spec.slug}")

                activated = await client.post(f"/api/admin/products/{product_id}/activate")
                if activated.status_code != 200:
                    _fail(activated, f"Activate product {spec.sku}")

                published = await client.post(f"/api/admin/landings/{landing_id}/publish")
                if published.status_code != 200:
                    _fail(published, f"Publish landing {spec.slug}")

                for block_type, slot_index, block_config in spec.blocks:
                    placed = await client.post(
                        f"/api/admin/landings/{landing_id}/blocks",
                        json={
                            "block_type": block_type,
                            "slot_index": slot_index,
                            "config": block_config,
                        },
                    )
                    if placed.status_code != 201:
                        _fail(placed, f"Conversion component {block_type} on {spec.slug}")

                # Analytics need traffic to be worth looking at: views always
                # outnumber clicks, clicks outnumber orders.
                for index in range(12):
                    view = await client.post(
                        f"/api/public/landings/{spec.slug}/view",
                        json={"landing_slug": spec.slug},
                    )
                    if view.status_code != 200:
                        _fail(view, f"Landing view {spec.slug}")
                    if index % 3 == 0:
                        click = await client.post(f"/api/public/landings/{spec.slug}/cta-click")
                        if click.status_code != 200:
                            _fail(click, f"CTA click {spec.slug}")

            for order in ORDERS:
                department, city = _canonical_location(order["department"], order["city"])
                created_order = await client.post(
                    "/api/public/orders",
                    json={
                        "landing_slug": order["slug"],
                        "full_name": order["full_name"],
                        "phone": order["phone"],
                        "department": department,
                        "city": city,
                        "address": order["address"],
                        "quantity": order["quantity"],
                    },
                    headers={
                        "cf-connecting-ip": order["ip"],
                        "user-agent": "Mozilla/5.0 (Linux; Android 13) SeedScript/1.0",
                    },
                )
                if created_order.status_code != 201:
                    _fail(created_order, f"Order for {order['slug']}")

        return {
            "products": await db.product.count(),
            "landings_published": await db.landing.count(where={"status": "published"}),
            "banners": await db.banner.count(),
            "image_variants": await db.imagevariant.count(),
            "conversion_blocks": await db.landingblock.count(),
            "orders_pending": await db.order.count(where={"status": "pending"}),
            "orders_flagged": await db.order.count(where={"status": "flagged_fraud"}),
            "fraud_flags": await db.fraudflag.count(),
            "landing_views": await db.landingview.count(),
            "cta_clicks": await db.ctaclick.count(),
            "blacklist_entries": await db.blacklistentry.count(),
        }
    finally:
        app.dependency_overrides.pop(get_geoip_resolver, None)
        await disconnect_db()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed development sample data.")
    parser.add_argument("--username", default="admin", help="Administrator username to act as.")
    parser.add_argument(
        "--password",
        default=None,
        help="Administrator password. Defaults to the ADMIN_PASSWORD environment variable.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    password = args.password or os.getenv("ADMIN_PASSWORD")
    if not password:
        print("A password is required: pass --password or set ADMIN_PASSWORD.", file=sys.stderr)
        return 2

    counts = asyncio.run(seed(username=args.username, password=password))
    print("Development data seeded:")
    for key, value in counts.items():
        print(f"  {key}: {value}")
    for spec in CATALOG:
        print(f"  landing: /p/{spec.slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
