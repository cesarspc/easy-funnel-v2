"""Validation for creating one complete published landing from a template.

The bulk endpoint accepts public URLs because automation outside the dashboard
already stages source files in the configured R2 bucket.  A URL is only an
identifier here: the backend resolves it back to an ``originals/`` object key
and reads it with the authenticated R2 client.  It never performs an arbitrary
HTTP request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit

from app.domains.landings.blocks import (
    BLOCK_OFFERS_PRICE,
    BLOCK_VIDEO_CAROUSEL,
    MAX_VIDEOS_PER_CAROUSEL,
)
from app.domains.landings.errors import LandingValidationError


@dataclass(frozen=True)
class TemplateMediaRequirement:
    block_index: int
    block_type: str
    offer_quantities: tuple[int, ...] = ()
    minimum_videos: int | None = None
    maximum_videos: int | None = None


def r2_original_object_key(public_url: str, *, public_host: str) -> str:
    """Return the R2 object key represented by a configured public URL.

    Host, scheme, optional public-host base path, query and fragment are all
    checked explicitly.  Restricting the result to one direct child of
    ``originals/`` keeps client-controlled paths away from every other bucket
    namespace and makes the accepted shape match ``original_object_key``.
    """

    if not isinstance(public_url, str) or not public_url.strip():
        raise LandingValidationError("original_url", "La URL original de R2 es obligatoria.")

    candidate = urlsplit(public_url.strip())
    configured = urlsplit(public_host.rstrip("/"))
    if (
        candidate.scheme != configured.scheme
        or candidate.netloc != configured.netloc
        or candidate.username is not None
        or candidate.password is not None
        or candidate.query
        or candidate.fragment
    ):
        raise LandingValidationError(
            "original_url", "La URL debe pertenecer al host público de R2 configurado."
        )

    configured_path = configured.path.rstrip("/")
    candidate_path = unquote(candidate.path)
    prefix = f"{configured_path}/" if configured_path else "/"
    if not candidate_path.startswith(prefix):
        raise LandingValidationError(
            "original_url", "La URL debe pertenecer al host público de R2 configurado."
        )
    object_key = candidate_path[len(prefix) :]
    if not object_key.startswith("originals/"):
        raise LandingValidationError(
            "original_url", "La URL debe señalar un archivo dentro de originals/."
        )
    filename = object_key.removeprefix("originals/")
    if not filename or "/" in filename or filename in {".", ".."}:
        raise LandingValidationError(
            "original_url", "La URL original de R2 no tiene una ruta válida."
        )
    return object_key


def describe_media_requirements(
    blocks: list[dict[str, Any]], *, offer_count: int
) -> list[TemplateMediaRequirement]:
    """Describe every template block that accepts or requires media."""

    requirements: list[TemplateMediaRequirement] = []
    for block_index, block in enumerate(blocks):
        block_type = block["block_type"]
        if block_type == BLOCK_VIDEO_CAROUSEL:
            requirements.append(
                TemplateMediaRequirement(
                    block_index=block_index,
                    block_type=block_type,
                    minimum_videos=0,
                    maximum_videos=MAX_VIDEOS_PER_CAROUSEL,
                )
            )
        elif block_type == BLOCK_OFFERS_PRICE:
            requirements.append(
                TemplateMediaRequirement(
                    block_index=block_index,
                    block_type=block_type,
                    offer_quantities=tuple(range(1, offer_count + 1)),
                )
            )
    return requirements


def validate_block_asset_assignments(
    requirements: list[TemplateMediaRequirement], assignments: list[dict[str, Any]]
) -> dict[int, dict[str, Any]]:
    """Validate block-index addressing and exact per-block asset cardinality."""

    by_index: dict[int, dict[str, Any]] = {}
    for assignment in assignments:
        block_index = assignment.get("block_index")
        if isinstance(block_index, bool) or not isinstance(block_index, int):
            raise LandingValidationError("block_assets", "Cada asignación necesita block_index.")
        if block_index in by_index:
            raise LandingValidationError(
                "block_assets", f"El bloque {block_index} aparece más de una vez."
            )
        by_index[block_index] = assignment

    expected = {requirement.block_index: requirement for requirement in requirements}
    unknown = sorted(set(by_index) - set(expected))
    if unknown:
        raise LandingValidationError(
            "block_assets", f"Los bloques {unknown} no aceptan archivos en esta plantilla."
        )

    for block_index, requirement in expected.items():
        assignment = by_index.get(block_index, {})
        videos = assignment.get("videos") or []
        offer_images = assignment.get("offer_images") or []
        if requirement.block_type == BLOCK_VIDEO_CAROUSEL:
            if offer_images:
                raise LandingValidationError(
                    "block_assets", f"El bloque {block_index} solo acepta videos."
                )
            if len(videos) > MAX_VIDEOS_PER_CAROUSEL:
                raise LandingValidationError(
                    "block_assets",
                    f"El carrusel {block_index} admite máximo {MAX_VIDEOS_PER_CAROUSEL} videos.",
                )
        else:
            if videos:
                raise LandingValidationError(
                    "block_assets", f"El bloque {block_index} solo acepta imágenes de ofertas."
                )
            quantities = [item.get("quantity") for item in offer_images]
            if len(quantities) != len(set(quantities)):
                raise LandingValidationError(
                    "offer_images", f"El bloque {block_index} repite una cantidad de oferta."
                )
            expected_quantities = list(requirement.offer_quantities)
            if sorted(quantities) != expected_quantities:
                raise LandingValidationError(
                    "offer_images",
                    (
                        f"El bloque {block_index} requiere exactamente una imagen para "
                        f"cada cantidad: {expected_quantities}."
                    ),
                )

    # Offer blocks are mandatory; video blocks may be omitted to mean zero.
    for requirement in requirements:
        if requirement.block_type == BLOCK_OFFERS_PRICE and requirement.block_index not in by_index:
            raise LandingValidationError(
                "offer_images",
                f"El bloque {requirement.block_index} requiere imágenes para todas sus ofertas.",
            )
    return by_index


__all__ = [
    "TemplateMediaRequirement",
    "describe_media_requirements",
    "r2_original_object_key",
    "validate_block_asset_assignments",
]
