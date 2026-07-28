"""Prisma client wrapper and repository classes."""

from app.db.client import connect_db, disconnect_db, get_db, utcnow
from app.db.repositories import (
    AdminUserRepository,
    AuditLogRepository,
    BannerRepository,
    BlacklistEntryRepository,
    CtaClickRepository,
    FraudConfigRepository,
    FraudFlagRepository,
    GeoIpRuleRepository,
    ImageAssetRepository,
    ImageVariantRepository,
    LandingRepository,
    LandingViewRepository,
    OrderRepository,
    ProductRepository,
)

__all__ = [
    "get_db",
    "connect_db",
    "disconnect_db",
    "utcnow",
    "ProductRepository",
    "LandingRepository",
    "BannerRepository",
    "ImageAssetRepository",
    "ImageVariantRepository",
    "OrderRepository",
    "FraudFlagRepository",
    "FraudConfigRepository",
    "BlacklistEntryRepository",
    "GeoIpRuleRepository",
    "LandingViewRepository",
    "CtaClickRepository",
    "AdminUserRepository",
    "AuditLogRepository",
]
