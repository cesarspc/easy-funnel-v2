"""ProductLifecycleService: product creation + lifecycle transitions.

Composes `app.domains.products` validation/lifecycle rules with the
`ProductRepository` / `LandingRepository` / `AuditLogRepository`, running
every mutation inside one Prisma transaction so a product is never left
without its single draft landing, and a rejected transition never partially
mutates the record (Requirements 2.1, 2.7, 2.9-2.21).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from prisma import Json, Prisma
from prisma.models import Landing, Product
from prisma.types import ProductUpdateInput

from app.db.client import utcnow
from app.db.repositories import (
    AuditLogRepository,
    LandingBlockRepository,
    LandingRepository,
    ProductRepository,
)
from app.domains.landings.blocks import BLOCK_ANNOUNCEMENT_BAR, validate_block_config
from app.domains.products.errors import (
    DuplicateSkuError,
    ProductNotFoundError,
    ProductValidationError,
    RetiredProductError,
)
from app.domains.products.lifecycle import (
    next_status_on_activate,
    next_status_on_pause,
    next_status_on_retire,
)
from app.domains.products.validation import (
    validate_creation_status,
    validate_description,
    validate_name,
    validate_price,
    validate_sku,
)
from app.domains.products.variants import validate_variant_options

_TransitionFn = Callable[[int, str], str]

# Draft landings are created with a sensible, valid-by-construction default
# configuration; the Administrator edits slug/CTA/presentation via the
# landings domain (task 7) before publishing.
_DEFAULT_DRAFT_CTA_MODE = "after_every"
_DEFAULT_DRAFT_FORM_PRESENTATION = "inline"

# Every new landing starts with one announcement bar above everything (slot 0),
# so a merchant sees the component in place rather than having to know to add
# it. Content is a placeholder the merchant is expected to rewrite; the
# component itself (and its slot) can be edited or removed like any other.
_DEFAULT_ANNOUNCEMENT_TEXT = "Envío gratis + Paga al recibir"
_ANNOUNCEMENT_SLOT_INDEX = 0


@dataclass(frozen=True)
class ProductCreationResult:
    product: Product
    landing: Landing


class ProductLifecycleService:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def create_product(
        self,
        *,
        name: str,
        sku: str,
        price: Decimal | str,
        description: str = "",
        status: str | None = None,
        variant_options: list[dict] | None = None,
        actor: str,
    ) -> ProductCreationResult:
        """Validate, then atomically create a Product and its single draft
        Landing (Requirements 2.1, 2.2-2.6, 2.7, 2.10).

        Raises `ProductValidationError` on any invalid field and
        `DuplicateSkuError` if the SKU is already used by any non-retired
        or retired product — neither the product nor a landing is created
        on failure.
        """
        validated_name = validate_name(name)
        validated_description = validate_description(description)
        validated_price = validate_price(price)
        validated_sku = validate_sku(sku)
        validated_status = validate_creation_status(status)
        validated_variant_options = validate_variant_options(variant_options)

        async with self._db.tx() as tx:
            products = ProductRepository(tx)
            landings = LandingRepository(tx)
            blocks = LandingBlockRepository(tx)
            audit_log = AuditLogRepository(tx)

            existing = await products.get_by_sku(validated_sku)
            if existing is not None:
                raise DuplicateSkuError(validated_sku)

            product = await products.create(
                {
                    "name": validated_name,
                    "description": validated_description,
                    "price": validated_price,
                    "sku": validated_sku,
                    "status": validated_status,
                    "variantOptions": Json(validated_variant_options),
                }
            )
            landing = await landings.create(
                {
                    "productId": product.id,
                    "slug": f"draft-{product.id}",
                    "ctaMode": _DEFAULT_DRAFT_CTA_MODE,
                    "formPresentation": _DEFAULT_DRAFT_FORM_PRESENTATION,
                }
            )
            announcement_config = validate_block_config(
                BLOCK_ANNOUNCEMENT_BAR, {"text": _DEFAULT_ANNOUNCEMENT_TEXT}
            )
            await blocks.create(
                {
                    "landingId": landing.id,
                    "blockType": BLOCK_ANNOUNCEMENT_BAR,
                    "slotIndex": _ANNOUNCEMENT_SLOT_INDEX,
                    "orderIndex": 0,
                    "config": Json(announcement_config),
                    "enabled": True,
                }
            )
            await audit_log.record(
                actor=actor,
                action="product.create",
                target_type="product",
                target_id=str(product.id),
                result="success",
            )

        return ProductCreationResult(product=product, landing=landing)

    async def update_product(
        self,
        product_id: int,
        *,
        updates: dict[str, str | Decimal],
        actor: str,
    ) -> Product:
        """Validate and atomically update mutable product catalog fields.

        Variant options and lifecycle status deliberately stay outside this
        operation. Existing Orders keep their captured unit/total prices, while
        future landing views and orders use the Product's new catalog price.
        """
        allowed_fields = {"name", "sku", "price", "description"}
        unsupported = set(updates) - allowed_fields
        if unsupported:
            raise ProductValidationError(
                next(iter(sorted(unsupported))), "This product field cannot be edited."
            )
        if not updates:
            raise ProductValidationError("request", "Provide at least one product field to edit.")

        validated: ProductUpdateInput = {}
        if "name" in updates:
            validated["name"] = validate_name(str(updates["name"]))
        if "description" in updates:
            validated["description"] = validate_description(str(updates["description"]))
        if "price" in updates:
            validated["price"] = validate_price(updates["price"])
        if "sku" in updates:
            validated["sku"] = validate_sku(str(updates["sku"]))

        async with self._db.tx() as tx:
            products = ProductRepository(tx)
            product = await products.get_by_id(product_id)
            if product is None:
                raise ProductNotFoundError(product_id)
            if product.status == "retired":
                raise RetiredProductError(product_id)

            if "sku" in validated and validated["sku"] != product.sku:
                existing = await products.get_by_sku(validated["sku"])
                if existing is not None:
                    raise DuplicateSkuError(validated["sku"])

            updated = await products.update(product_id, validated)
            if updated is None:
                raise ProductNotFoundError(product_id)
            await AuditLogRepository(tx).record(
                actor=actor,
                action="product.update",
                target_type="product",
                target_id=str(product_id),
                result="success",
            )
            return updated

    async def activate(self, product_id: int, *, actor: str) -> Product:
        return await self._transition(
            product_id,
            actor=actor,
            action="product.activate",
            compute_next=next_status_on_activate,
        )

    async def pause(self, product_id: int, *, actor: str) -> Product:
        return await self._transition(
            product_id,
            actor=actor,
            action="product.pause",
            compute_next=next_status_on_pause,
        )

    async def retire(self, product_id: int, *, actor: str) -> Product:
        """Soft-delete (retire) a product (Requirements 2.13-2.16, 2.21).

        Never performs physical erasure: only the `status`/`retired_at`
        columns change. Historical Landing/Banner/Order/FraudFlag/AuditLog
        references are untouched (enforced by restrict FKs at the schema
        level, task 3).
        """
        product = await self._transition(
            product_id, actor=actor, action="product.retire", compute_next=next_status_on_retire
        )
        async with self._db.tx() as tx:
            updated = await ProductRepository(tx).update(product.id, {"retiredAt": utcnow()})
        return updated if updated is not None else product

    async def _transition(
        self,
        product_id: int,
        *,
        actor: str,
        action: str,
        compute_next: _TransitionFn,
    ) -> Product:
        async with self._db.tx() as tx:
            products = ProductRepository(tx)
            audit_log = AuditLogRepository(tx)

            product = await products.get_by_id(product_id)
            if product is None:
                raise ProductNotFoundError(product_id)

            next_status = compute_next(product_id, product.status)

            updated = await products.update(product_id, {"status": next_status})
            if updated is None:
                raise ProductNotFoundError(product_id)

            await audit_log.record(
                actor=actor,
                action=action,
                target_type="product",
                target_id=str(product_id),
                result="success",
            )
            return updated
