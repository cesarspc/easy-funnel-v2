"""Runtime platform parameters read from the admin-editable store settings.

Request handlers call `load_platform_config(db)` instead of reading constants
or environment variables, so market conventions (locale, currency, time zone,
phone rules) and the fulfillment integration change from Admin → Tienda
without a redeploy. A short in-process cache keeps the hot order path to one
settings read every few seconds; an update from this process invalidates it
immediately.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

from prisma import Prisma

from app.core.regional import DEFAULT_REGIONAL, PhoneRules, RegionalConfig

FulfillmentProvider = Literal["none", "mastershop"]
FULFILLMENT_PROVIDERS: frozenset[str] = frozenset({"none", "mastershop"})
CACHE_TTL_SECONDS = 5.0


@dataclass(frozen=True)
class FulfillmentConfig:
    provider: str
    mastershop_orders_url: str
    mastershop_timeout_seconds: float
    mastershop_api_key: str

    @property
    def mastershop_enabled(self) -> bool:
        return self.provider == "mastershop"


@dataclass(frozen=True)
class PlatformConfig:
    regional: RegionalConfig
    fulfillment: FulfillmentConfig


_cache: tuple[float, PlatformConfig] | None = None


def regional_from_store(store: Any) -> RegionalConfig:
    if store is None:
        return DEFAULT_REGIONAL
    return RegionalConfig(
        country_code=store.countryCode,
        locale=store.locale,
        currency=store.currency,
        time_zone=store.timeZone,
        phone=PhoneRules(
            country_code=store.phoneCountryCode,
            national_pattern=store.phoneNationalPattern,
        ),
    )


def fulfillment_from_store(store: Any) -> FulfillmentConfig:
    if store is None:
        return FulfillmentConfig("none", "", 5.0, "")
    return FulfillmentConfig(
        provider=store.fulfillmentProvider or "none",
        mastershop_orders_url=store.mastershopOrdersUrl or "",
        mastershop_timeout_seconds=float(store.mastershopTimeoutSeconds or 5),
        mastershop_api_key=store.mastershopApiKey or "",
    )


def platform_config_from_store(store: Any) -> PlatformConfig:
    return PlatformConfig(regional_from_store(store), fulfillment_from_store(store))


async def load_platform_config(db: Prisma, *, fresh: bool = False) -> PlatformConfig:
    """Return the current platform parameters, cached for a few seconds."""
    global _cache
    now = time.monotonic()
    if not fresh and _cache is not None and now - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]
    store = await db.storesettings.find_unique(where={"id": 1})
    config = platform_config_from_store(store)
    _cache = (now, config)
    return config


def invalidate_platform_config() -> None:
    global _cache
    _cache = None
