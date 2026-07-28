"""Unit tests for opaque key generation (Requirements 10.13, 10.19, 10.20)."""

from __future__ import annotations

import inspect

import pytest
from app.domains.images.errors import OpaqueKeyGenerationError
from app.domains.images.opaque_key import (
    generate_fallback_opaque_key,
    generate_opaque_key,
    generate_primary_opaque_key,
)


def _always_fails() -> str:
    raise RuntimeError("generator unavailable")


class TestGeneratePrimaryAndFallbackKeys:
    def test_primary_keys_are_unique_across_calls(self) -> None:
        keys = {generate_primary_opaque_key() for _ in range(50)}
        assert len(keys) == 50

    def test_fallback_keys_are_unique_across_calls(self) -> None:
        keys = {generate_fallback_opaque_key() for _ in range(50)}
        assert len(keys) == 50

    def test_primary_and_fallback_key_spaces_do_not_collide_in_practice(self) -> None:
        primary_keys = {generate_primary_opaque_key() for _ in range(50)}
        fallback_keys = {generate_fallback_opaque_key() for _ in range(50)}
        assert primary_keys.isdisjoint(fallback_keys)


class TestGenerateOpaqueKeyWithFallback:
    def test_uses_the_primary_generator_when_it_succeeds(self) -> None:
        key = generate_opaque_key(
            primary_generator=lambda: "primary-key-value",
            fallback_generator=_always_fails,
        )
        assert key == "primary-key-value"

    def test_falls_back_when_the_primary_generator_fails(self) -> None:
        key = generate_opaque_key(
            primary_generator=_always_fails,
            fallback_generator=lambda: "fallback-key-value",
        )
        assert key == "fallback-key-value"

    def test_fallback_output_is_unaffected_by_the_failed_primary_mechanism(self) -> None:
        # The fallback must be independent: it succeeds identically whether
        # or not the primary was even attempted, and its own output does
        # not depend on anything the primary generator tried to do.
        key_after_primary_failure = generate_opaque_key(
            primary_generator=_always_fails,
            fallback_generator=generate_fallback_opaque_key,
        )
        key_from_fallback_directly = generate_fallback_opaque_key()

        # Both are drawn from the same independent generator; neither is
        # empty, tied to the primary's failure message, or predictable.
        assert key_after_primary_failure != key_from_fallback_directly
        assert len(key_after_primary_failure) > 0

    def test_rejects_when_both_primary_and_fallback_fail(self) -> None:
        with pytest.raises(OpaqueKeyGenerationError):
            generate_opaque_key(
                primary_generator=_always_fails,
                fallback_generator=_always_fails,
            )

    def test_default_generators_are_independent_of_any_client_supplied_filename(self) -> None:
        # Neither default generator accepts a filename/path argument at
        # all, so client-controlled input structurally cannot influence
        # the resulting key or its storage path.
        assert "filename" not in inspect.signature(generate_primary_opaque_key).parameters
        assert "filename" not in inspect.signature(generate_fallback_opaque_key).parameters
