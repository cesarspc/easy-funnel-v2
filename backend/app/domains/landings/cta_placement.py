"""CTA placement configuration and computation (Requirements 3.9-3.15).

Three modes:
    after_every      -> a CTA after every banner
    every_n           -> a CTA after every completed `interval` (1-15) banners
    fixed_positions   -> CTAs only after the configured 1-based banner
                         positions (a non-empty set, unique, within range)

`CtaConfig` is the validated, persistable representation; `compute_cta_positions`
turns a validated config plus a banner count into the concrete list of
banner positions (1-based) after which a CTA renders.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.landings.errors import LandingValidationError

CTA_MODE_AFTER_EVERY = "after_every"
CTA_MODE_EVERY_N = "every_n"
CTA_MODE_FIXED_POSITIONS = "fixed_positions"

ALLOWED_CTA_MODES = frozenset({CTA_MODE_AFTER_EVERY, CTA_MODE_EVERY_N, CTA_MODE_FIXED_POSITIONS})

INTERVAL_MIN = 1
INTERVAL_MAX = 15


@dataclass(frozen=True)
class CtaConfig:
    mode: str
    interval: int | None = None
    positions: frozenset[int] | None = None


def validate_cta_config(
    mode: str,
    *,
    interval: int | None = None,
    positions: list[int] | None = None,
    banner_count: int | None = None,
) -> CtaConfig:
    """Validate a CTA configuration for the given mode (Requirements 3.9-3.11, 3.15).

    `banner_count`, when given, additionally validates that fixed positions
    fall within the current banner sequence (used at publish time).
    """
    if mode not in ALLOWED_CTA_MODES:
        raise LandingValidationError("cta_mode", f"Unsupported CTA mode '{mode}'.")

    if mode == CTA_MODE_AFTER_EVERY:
        return CtaConfig(mode=mode)

    if mode == CTA_MODE_EVERY_N:
        if interval is None or not (INTERVAL_MIN <= interval <= INTERVAL_MAX):
            raise LandingValidationError(
                "cta_interval",
                f"Interval must be an integer from {INTERVAL_MIN} to {INTERVAL_MAX}.",
            )
        return CtaConfig(mode=mode, interval=interval)

    # fixed_positions
    if not positions:
        raise LandingValidationError(
            "cta_positions", "Fixed positions must be a non-empty set of unique positions."
        )
    unique_positions = frozenset(positions)
    if len(unique_positions) != len(positions):
        raise LandingValidationError("cta_positions", "Fixed positions must be unique.")
    if any(p < 1 for p in unique_positions):
        raise LandingValidationError("cta_positions", "Fixed positions must be positive.")
    if banner_count is not None and any(p > banner_count for p in unique_positions):
        raise LandingValidationError(
            "cta_positions", "Fixed positions must be within the current banner sequence."
        )
    return CtaConfig(mode=mode, positions=unique_positions)


def compute_cta_positions(config: CtaConfig, banner_count: int) -> list[int]:
    """Return the 1-based banner positions after which a CTA renders.

    - `after_every`: every position from 1 to `banner_count`.
    - `every_n`: every position that completes an `interval`-sized group.
    - `fixed_positions`: exactly the configured positions that fall within
      `banner_count`, in ascending order.
    """
    if banner_count <= 0:
        return []

    if config.mode == CTA_MODE_AFTER_EVERY:
        return list(range(1, banner_count + 1))

    if config.mode == CTA_MODE_EVERY_N:
        assert config.interval is not None
        return list(range(config.interval, banner_count + 1, config.interval))

    # fixed_positions
    assert config.positions is not None
    return sorted(p for p in config.positions if p <= banner_count)
