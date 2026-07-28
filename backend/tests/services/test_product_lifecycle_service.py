"""Integration tests for ProductLifecycleService (Requirements 2.1-2.22).

Requires a real database (see tests/conftest.py) since the service composes
repositories inside a Prisma transaction.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.domains.products.errors import (
    DuplicateSkuError,
    InvalidProductTransitionError,
    ProductNotFoundError,
    ProductValidationError,
    RetiredProductError,
)
from app.services.product_lifecycle_service import ProductLifecycleService
from prisma import Prisma

from tests.db.conftest import requires_database


@requires_database
class TestCreateProduct:
    async def test_creates_product_and_a_single_draft_landing(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)

        result = await service.create_product(
            name="Producto Uno",
            sku="SKU-CREATE-1",
            price=Decimal("49.99"),
            actor="admin",
        )

        assert result.product.name == "Producto Uno"
        assert result.product.status == "paused"
        assert result.landing.productId == result.product.id
        assert result.landing.status == "draft"

    async def test_default_status_is_paused_when_not_specified(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)

        result = await service.create_product(
            name="Producto Dos", sku="SKU-CREATE-2", price=Decimal("10.00"), actor="admin"
        )

        assert result.product.status == "paused"

    async def test_explicit_active_status_is_honored(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)

        result = await service.create_product(
            name="Producto Tres",
            sku="SKU-CREATE-3",
            price=Decimal("10.00"),
            status="active",
            actor="admin",
        )

        assert result.product.status == "active"

    async def test_duplicate_sku_is_rejected_and_creates_nothing(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)
        await service.create_product(
            name="Original", sku="SKU-DUPE-SVC", price=Decimal("10.00"), actor="admin"
        )

        with pytest.raises(DuplicateSkuError):
            await service.create_product(
                name="Duplicado", sku="SKU-DUPE-SVC", price=Decimal("20.00"), actor="admin"
            )

        products = await db.product.find_many(where={"sku": "SKU-DUPE-SVC"})
        assert len(products) == 1

    async def test_invalid_name_is_rejected_and_creates_nothing(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)

        with pytest.raises(ProductValidationError):
            await service.create_product(
                name="", sku="SKU-INVALID-NAME", price=Decimal("10.00"), actor="admin"
            )

        products = await db.product.find_many(where={"sku": "SKU-INVALID-NAME"})
        assert len(products) == 0

    async def test_invalid_price_creates_no_product_or_landing(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)

        with pytest.raises(ProductValidationError):
            await service.create_product(
                name="Producto Precio Malo",
                sku="SKU-INVALID-PRICE",
                price=Decimal("0.00"),
                actor="admin",
            )

        products = await db.product.find_many(where={"sku": "SKU-INVALID-PRICE"})
        assert len(products) == 0


@requires_database
class TestActivatePauseRetire:
    async def test_activate_a_paused_product(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)
        result = await service.create_product(
            name="Activable", sku="SKU-ACTIVATE-1", price=Decimal("10.00"), actor="admin"
        )

        activated = await service.activate(result.product.id, actor="admin")

        assert activated.status == "active"

    async def test_activating_an_already_active_product_is_rejected_without_mutation(
        self, db: Prisma
    ) -> None:
        service = ProductLifecycleService(db)
        result = await service.create_product(
            name="Ya Activo",
            sku="SKU-ACTIVATE-2",
            price=Decimal("10.00"),
            status="active",
            actor="admin",
        )

        with pytest.raises(InvalidProductTransitionError):
            await service.activate(result.product.id, actor="admin")

        unchanged = await db.product.find_unique(where={"id": result.product.id})
        assert unchanged is not None
        assert unchanged.status == "active"

    async def test_pause_an_active_product(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)
        result = await service.create_product(
            name="Pausable",
            sku="SKU-PAUSE-1",
            price=Decimal("10.00"),
            status="active",
            actor="admin",
        )

        paused = await service.pause(result.product.id, actor="admin")

        assert paused.status == "paused"

    async def test_retire_preserves_landing_reference(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)
        result = await service.create_product(
            name="Retirable", sku="SKU-RETIRE-1", price=Decimal("10.00"), actor="admin"
        )

        retired = await service.retire(result.product.id, actor="admin")

        assert retired.status == "retired"
        assert retired.retiredAt is not None
        landing_still_exists = await db.landing.find_unique(where={"id": result.landing.id})
        assert landing_still_exists is not None
        assert landing_still_exists.productId == retired.id

    async def test_retiring_an_already_retired_product_is_rejected(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)
        result = await service.create_product(
            name="Doble Retiro", sku="SKU-RETIRE-2", price=Decimal("10.00"), actor="admin"
        )
        await service.retire(result.product.id, actor="admin")

        with pytest.raises(InvalidProductTransitionError):
            await service.retire(result.product.id, actor="admin")

    async def test_activating_a_retired_product_is_rejected(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)
        result = await service.create_product(
            name="Retirado Luego Activar",
            sku="SKU-RETIRE-3",
            price=Decimal("10.00"),
            actor="admin",
        )
        await service.retire(result.product.id, actor="admin")

        with pytest.raises(RetiredProductError):
            await service.activate(result.product.id, actor="admin")

    async def test_transition_on_unknown_product_raises_not_found(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)

        with pytest.raises(ProductNotFoundError):
            await service.activate(999_999_999, actor="admin")


@requires_database
class TestAuditTrail:
    async def test_product_create_is_audited(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)

        result = await service.create_product(
            name="Auditado", sku="SKU-AUDIT-CREATE", price=Decimal("10.00"), actor="admin-x"
        )

        entries = await db.auditlog.find_many(
            where={"targetType": "product", "targetId": str(result.product.id)}
        )
        assert any(e.action == "product.create" for e in entries)
        assert all(e.actor == "admin-x" for e in entries)

    async def test_retire_is_audited(self, db: Prisma) -> None:
        service = ProductLifecycleService(db)
        result = await service.create_product(
            name="Auditado Retiro", sku="SKU-AUDIT-RETIRE", price=Decimal("10.00"), actor="admin-y"
        )

        await service.retire(result.product.id, actor="admin-y")

        entries = await db.auditlog.find_many(
            where={"targetType": "product", "targetId": str(result.product.id)}
        )
        assert any(e.action == "product.retire" for e in entries)
