"""Landing/banner domain: slug validation, banner ordering, CTA placement,
publication validation, and the public not-found policy.

Pure functions only — no I/O. `LandingPublicationService` (app/services)
composes these with repositories inside Prisma transactions.
"""

from app.domains.landings.alt_text import (
    ALT_TEXT_MAX_LENGTH,
    ALT_TEXT_MIN_LENGTH,
    validate_alt_text,
)
from app.domains.landings.banner_ordering import (
    MAX_BANNERS_PER_LANDING,
    contiguous_indices,
    next_append_index,
    reorder,
    validate_can_add_banner,
)
from app.domains.landings.cta_background import (
    SOURCE_ABOVE,
    SOURCE_BELOW,
    SOURCE_BLEND,
    SOURCE_FALLBACK,
    BannerEdges,
    CtaBandBackground,
    compute_cta_backgrounds,
)
from app.domains.landings.cta_band_style import (
    ALLOWED_CTA_BAND_STYLES,
    CTA_BAND_STYLE_GRADIENT,
    CTA_BAND_STYLE_SOLID,
    validate_cta_band_style,
)
from app.domains.landings.cta_placement import (
    ALLOWED_CTA_MODES,
    CTA_MODE_AFTER_EVERY,
    CTA_MODE_EVERY_N,
    CTA_MODE_FIXED_POSITIONS,
    CtaConfig,
    compute_cta_positions,
    validate_cta_config,
)
from app.domains.landings.errors import (
    BannerLimitExceededError,
    BannerNotFoundError,
    DuplicateSlugError,
    LandingNotFoundError,
    LandingValidationError,
    PublicationValidationError,
)
from app.domains.landings.form_presentation import (
    ALLOWED_FORM_PRESENTATIONS,
    FORM_PRESENTATION_INLINE,
    FORM_PRESENTATION_MODAL,
    validate_form_presentation,
)
from app.domains.landings.slug import validate_slug_format

__all__ = [
    "LandingValidationError",
    "DuplicateSlugError",
    "LandingNotFoundError",
    "BannerNotFoundError",
    "BannerLimitExceededError",
    "PublicationValidationError",
    "validate_slug_format",
    "ALT_TEXT_MIN_LENGTH",
    "ALT_TEXT_MAX_LENGTH",
    "validate_alt_text",
    "FORM_PRESENTATION_INLINE",
    "FORM_PRESENTATION_MODAL",
    "ALLOWED_FORM_PRESENTATIONS",
    "validate_form_presentation",
    "MAX_BANNERS_PER_LANDING",
    "validate_can_add_banner",
    "next_append_index",
    "reorder",
    "contiguous_indices",
    "CTA_MODE_AFTER_EVERY",
    "CTA_MODE_EVERY_N",
    "CTA_MODE_FIXED_POSITIONS",
    "ALLOWED_CTA_MODES",
    "CtaConfig",
    "validate_cta_config",
    "compute_cta_positions",
    "BannerEdges",
    "CtaBandBackground",
    "compute_cta_backgrounds",
    "SOURCE_BLEND",
    "SOURCE_ABOVE",
    "SOURCE_BELOW",
    "SOURCE_FALLBACK",
    "CTA_BAND_STYLE_GRADIENT",
    "CTA_BAND_STYLE_SOLID",
    "ALLOWED_CTA_BAND_STYLES",
    "validate_cta_band_style",
]
