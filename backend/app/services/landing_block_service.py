"""LandingBlockService: place, edit, move, and remove a Landing's conversion
components (Requirements 3.27-3.31).

Composes `app.domains.landings.blocks` (the fixed component vocabulary, slot
bounds, and per-type content validation) with `LandingBlockRepository` and
`AuditLogRepository` inside Prisma transactions.

Two invariants this service owns:

- **Validate everything before writing anything.** A rejected slot leaves the
  stored content untouched, and a rejected content field leaves the stored slot
  untouched, so a half-applied component never reaches the page.
- **One component per (slot, order).** `landing_blocks` carries a unique
  `(landing_id, slot_index, order_index)` constraint, so placing or moving a
  block into an occupied slot picks the next free order within that slot rather
  than failing on the merchant. Placement is a positioning gesture, not a
  puzzle the Administrator has to solve.
"""

from __future__ import annotations

from typing import Any

from prisma import Json, Prisma
from prisma.models import LandingBlock
from prisma.types import LandingBlockUpdateInput

from app.db.repositories import (
    AuditLogRepository,
    BannerRepository,
    LandingBlockRepository,
    LandingRepository,
)
from app.domains.landings.blocks import (
    MAX_ORDER_INDEX,
    slot_labels,
    validate_block_config,
    validate_block_type,
    validate_can_add_block,
    validate_slot_index,
)
from app.domains.landings.errors import (
    LandingNotFoundError,
    LandingValidationError,
)


class BlockNotFoundError(LandingValidationError):
    """Raised when a component id does not belong to the landing."""

    def __init__(self, block_id: int) -> None:
        super().__init__("block_id", f"Conversion component {block_id} was not found.")
        self.block_id = block_id


class LandingBlockService:
    def __init__(self, db: Prisma) -> None:
        self._db = db

    async def list_blocks(self, landing_id: int) -> list[LandingBlock]:
        blocks = LandingBlockRepository(self._db)
        return await blocks.list_for_landing(landing_id)

    async def describe_slots(self, landing_id: int) -> list[str]:
        """Human-readable labels for every placement slot of this landing.

        Derived from the same banner sequence and CTA positions the public page
        renders, so the dashboard's position list and the rendered result cannot
        disagree.
        """
        landing = await LandingRepository(self._db).get_by_id(landing_id)
        if landing is None:
            raise LandingNotFoundError(landing_id)
        banners = await BannerRepository(self._db).list_for_landing(landing_id)
        return slot_labels(len(banners), list(landing.ctaPositions or []))

    async def create_block(
        self,
        landing_id: int,
        *,
        block_type: str,
        slot_index: int,
        config: Any,
        enabled: bool = True,
        actor: str,
    ) -> LandingBlock:
        """Place a new component in `slot_index`."""
        validated_type = validate_block_type(block_type)
        validated_slot = validate_slot_index(slot_index)
        validated_config = validate_block_config(validated_type, config)

        async with self._db.tx() as tx:
            landings = LandingRepository(tx)
            blocks = LandingBlockRepository(tx)
            audit_log = AuditLogRepository(tx)

            if await landings.get_by_id(landing_id) is None:
                raise LandingNotFoundError(landing_id)

            existing = await blocks.list_for_landing(landing_id)
            validate_can_add_block(len(existing))
            order_index = _next_order_in_slot(existing, validated_slot)

            block = await blocks.create(
                {
                    "landingId": landing_id,
                    "blockType": validated_type,
                    "slotIndex": validated_slot,
                    "orderIndex": order_index,
                    "config": Json(validated_config),
                    "enabled": enabled,
                }
            )

            await audit_log.record(
                actor=actor,
                action="landing_block.create",
                target_type="landing_block",
                target_id=str(block.id),
                result="success",
            )
            return block

    async def update_block(
        self,
        landing_id: int,
        block_id: int,
        *,
        slot_index: int | None = None,
        config: Any = None,
        enabled: bool | None = None,
        actor: str,
    ) -> LandingBlock:
        """Update one component's content, position, and/or enabled state."""
        async with self._db.tx() as tx:
            landings = LandingRepository(tx)
            blocks = LandingBlockRepository(tx)
            audit_log = AuditLogRepository(tx)

            if await landings.get_by_id(landing_id) is None:
                raise LandingNotFoundError(landing_id)

            stored = await blocks.list_for_landing(landing_id)
            block = next((item for item in stored if item.id == block_id), None)
            if block is None:
                raise BlockNotFoundError(block_id)

            data: LandingBlockUpdateInput = {}

            if config is not None:
                data["config"] = Json(validate_block_config(block.blockType, config))

            if slot_index is not None:
                validated_slot = validate_slot_index(slot_index)
                if validated_slot != block.slotIndex:
                    siblings = [item for item in stored if item.id != block_id]
                    data["slotIndex"] = validated_slot
                    data["orderIndex"] = _next_order_in_slot(siblings, validated_slot)

            if enabled is not None:
                data["enabled"] = enabled

            if not data:
                return block

            updated = await blocks.update(block_id, data)
            if updated is None:
                raise BlockNotFoundError(block_id)

            await audit_log.record(
                actor=actor,
                action="landing_block.update",
                target_type="landing_block",
                target_id=str(block_id),
                result="success",
            )
            return updated

    async def reorder_blocks(
        self, landing_id: int, ordered_block_ids: list[int], *, actor: str
    ) -> list[LandingBlock]:
        """Reorder blocks inside their slots from one verified dashboard sequence.

        The request contains every block id so a stale page can never drop or
        duplicate a component. Slots remain unchanged; only their render order
        is normalized to contiguous indices.
        """
        async with self._db.tx() as tx:
            landings = LandingRepository(tx)
            blocks = LandingBlockRepository(tx)
            audit_log = AuditLogRepository(tx)

            if await landings.get_by_id(landing_id) is None:
                raise LandingNotFoundError(landing_id)

            stored = await blocks.list_for_landing(landing_id)
            stored_ids = [block.id for block in stored]
            if sorted(ordered_block_ids) != sorted(stored_ids):
                raise LandingValidationError(
                    "block_ids",
                    "El orden debe incluir cada componente de esta landing una sola vez.",
                )

            blocks_by_id = {block.id: block for block in stored}
            ids_by_slot: dict[int, list[int]] = {}
            for block_id in ordered_block_ids:
                slot = blocks_by_id[block_id].slotIndex
                ids_by_slot.setdefault(slot, []).append(block_id)

            # The database checks the unique slot/order pair for each update.
            # Park every value in a unique negative range before assigning the
            # compact final values, just like banner ordering does.
            for temporary_index, block_id in enumerate(stored_ids, start=1):
                await blocks.update(block_id, {"orderIndex": -temporary_index})
            for block_ids in ids_by_slot.values():
                for order_index, block_id in enumerate(block_ids):
                    await blocks.update(block_id, {"orderIndex": order_index})

            await audit_log.record(
                actor=actor,
                action="landing_block.reorder",
                target_type="landing",
                target_id=str(landing_id),
                result="success",
            )
            return await blocks.list_for_landing(landing_id)

    async def delete_block(self, landing_id: int, block_id: int, *, actor: str) -> None:
        async with self._db.tx() as tx:
            landings = LandingRepository(tx)
            blocks = LandingBlockRepository(tx)
            audit_log = AuditLogRepository(tx)

            if await landings.get_by_id(landing_id) is None:
                raise LandingNotFoundError(landing_id)

            stored = await blocks.list_for_landing(landing_id)
            if all(item.id != block_id for item in stored):
                raise BlockNotFoundError(block_id)

            await blocks.delete(block_id)
            await audit_log.record(
                actor=actor,
                action="landing_block.delete",
                target_type="landing_block",
                target_id=str(block_id),
                result="success",
            )


def _next_order_in_slot(blocks: list[LandingBlock], slot_index: int) -> int:
    """First free order index inside `slot_index`.

    Raises a field error only when a single slot is genuinely full, which takes
    ten components stacked between the same two elements — a layout no page
    wants, and the one case where silently picking another position would be
    worse than saying so.
    """
    used = {block.orderIndex for block in blocks if block.slotIndex == slot_index}
    for candidate in range(MAX_ORDER_INDEX + 1):
        if candidate not in used:
            return candidate
    raise LandingValidationError(
        "slot_index",
        "This position already holds the maximum number of components. Choose another position.",
    )
