"""Landing configuration templates: what a template carries, and when it applies.

Two properties under test, both of them the reason this feature needs a guard
rather than a best effort:

1. **The banner-count gate is exact in both directions.** For any pair of
   counts, `ensure_banner_count_matches` raises unless they are equal, and the
   message names both numbers — a merchant told only "must have 5" still has to
   count rows to know whether to add or remove.

2. **A round trip preserves the funnel and drops nothing silently.** For any
   landing configuration, `snapshot_config` followed by `parse_template_config`
   returns the same CTA placement, form presentation, offers, and accents, and
   never returns a key outside `TEMPLATE_CONFIG_FIELDS` — in particular never
   `slug`, `status`, or anything identifying a product, since applying a
   template must not be able to rename or publish a page.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.domains.landings.banner_ordering import MAX_BANNERS_PER_LANDING
from app.domains.landings.blocks import (
    BLOCK_COD_ASSURANCE,
    BLOCK_FAQ,
    BLOCK_GUARANTEE,
    MAX_BLOCKS_PER_LANDING,
    MAX_ORDER_INDEX,
)
from app.domains.landings.errors import LandingValidationError
from app.domains.landings.templates import (
    MAX_TEMPLATE_NAME_LENGTH,
    TEMPLATE_CONFIG_FIELDS,
    ensure_banner_count_matches,
    parse_template_blocks,
    parse_template_config,
    snapshot_blocks,
    snapshot_config,
    validate_template_banner_count,
    validate_template_name,
)
from hypothesis import given
from hypothesis import strategies as st


def landing_row(**overrides: object) -> SimpleNamespace:
    """A stand-in for a Prisma Landing row, with the columns a template reads.

    A namespace rather than a real model keeps these tests pure: the snapshot
    functions only ever read attributes, and building a Prisma instance would
    drag a database dependency into a domain test for no added coverage.
    """
    defaults: dict[str, object] = {
        "ctaMode": "after_every",
        "ctaInterval": None,
        "ctaPositions": [],
        "ctaBandStyle": "gradient",
        "ctaText": None,
        "ctaAnimation": None,
        "ctaTextOverrides": {},
        "ctaColorModes": {},
        "formPresentation": "inline",
        "accentColor": "#1a7a4c",
        "formAccentColor": None,
        "blocksDarkMode": False,
        "offerCount": 3,
        "offers": [],
        # Deliberately present so a test can prove they are NOT snapshotted.
        "slug": "producto-demo",
        "status": "published",
        "productId": 42,
        "id": 7,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def block_row(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "id": 101,
        "blockType": BLOCK_COD_ASSURANCE,
        "slotIndex": 1,
        "orderIndex": 0,
        "config": {"note": "Cobertura nacional"},
        "enabled": True,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestTemplateName:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Suplementos", "Suplementos"),
            ("  Con espacios  ", "Con espacios"),
            ("a" * MAX_TEMPLATE_NAME_LENGTH, "a" * MAX_TEMPLATE_NAME_LENGTH),
        ],
    )
    def test_accepts_and_trims(self, raw: str, expected: str) -> None:
        assert validate_template_name(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", None, 5, [], {}])
    def test_rejects_blank_and_non_text(self, raw: object) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_template_name(raw)  # type: ignore[arg-type]
        assert excinfo.value.field == "name"

    def test_rejects_a_name_past_the_column_bound(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_template_name("a" * (MAX_TEMPLATE_NAME_LENGTH + 1))
        assert excinfo.value.field == "name"


class TestBannerCountGate:
    @given(count=st.integers(min_value=0, max_value=MAX_BANNERS_PER_LANDING))
    def test_equal_counts_always_pass(self, count: int) -> None:
        ensure_banner_count_matches(required=count, actual=count)

    @given(
        required=st.integers(min_value=0, max_value=MAX_BANNERS_PER_LANDING),
        actual=st.integers(min_value=0, max_value=MAX_BANNERS_PER_LANDING),
    )
    def test_unequal_counts_always_fail_on_the_banner_count_field(
        self, required: int, actual: int
    ) -> None:
        if required == actual:
            return
        with pytest.raises(LandingValidationError) as excinfo:
            ensure_banner_count_matches(required=required, actual=actual)
        assert excinfo.value.field == "banner_count"

    @given(
        required=st.integers(min_value=0, max_value=MAX_BANNERS_PER_LANDING),
        actual=st.integers(min_value=0, max_value=MAX_BANNERS_PER_LANDING),
    )
    def test_the_message_names_both_counts(self, required: int, actual: int) -> None:
        """Both numbers, so the merchant knows whether to add or remove banners."""
        if required == actual:
            return
        with pytest.raises(LandingValidationError) as excinfo:
            ensure_banner_count_matches(required=required, actual=actual)
        message = excinfo.value.message
        assert str(required) in message
        assert str(actual) in message

    def test_singular_wording_for_one_banner(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            ensure_banner_count_matches(required=1, actual=4)
        assert "1 banner " in excinfo.value.message

    @pytest.mark.parametrize("raw", [-1, MAX_BANNERS_PER_LANDING + 1, "3", None, True])
    def test_stored_count_outside_the_cap_is_rejected(self, raw: object) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_template_banner_count(raw)
        assert excinfo.value.field == "banner_count"


class TestConfigSnapshot:
    def test_snapshot_carries_exactly_the_declared_fields(self) -> None:
        config = snapshot_config(landing_row())
        assert set(config) == set(TEMPLATE_CONFIG_FIELDS)

    @pytest.mark.parametrize("identity_field", ["slug", "status", "product_id", "id"])
    def test_snapshot_never_carries_identity(self, identity_field: str) -> None:
        """A template configures a funnel; it cannot rename or publish a page."""
        assert identity_field not in snapshot_config(landing_row())

    def test_snapshot_copies_the_stored_values(self) -> None:
        config = snapshot_config(
            landing_row(
                ctaMode="fixed_positions",
                ctaPositions=[1, 3],
                ctaText="Lo quiero",
                ctaAnimation="shake",
                ctaTextOverrides={"2": "Ahora"},
                ctaColorModes={"1": "dark"},
                formPresentation="modal",
                accentColor="#2563eb",
                formAccentColor="#e11d48",
                blocksAccentColor="#7c3aed",
                blocksDarkMode=True,
                offerCount=2,
            )
        )
        assert config["cta_mode"] == "fixed_positions"
        assert config["cta_positions"] == [1, 3]
        assert config["cta_text"] == "Lo quiero"
        assert config["cta_animation"] == "shake"
        assert config["cta_text_overrides"] == {"2": "Ahora"}
        assert config["cta_color_modes"] == {"1": "dark"}
        assert config["form_presentation"] == "modal"
        assert config["accent_color"] == "#2563eb"
        assert config["form_accent_color"] == "#e11d48"
        assert config["blocks_accent_color"] == "#7c3aed"
        assert config["blocks_dark_mode"] is True
        assert config["offer_count"] == 2

    def test_snapshot_does_not_alias_the_row(self) -> None:
        """Mutating the landing afterwards must not reach into a saved template."""
        overrides: dict[str, str] = {"2": "Ahora"}
        positions = [1, 2]
        row = landing_row(ctaTextOverrides=overrides, ctaPositions=positions)
        config = snapshot_config(row)

        overrides["3"] = "Injected"
        positions.append(3)

        assert config["cta_text_overrides"] == {"2": "Ahora"}
        assert config["cta_positions"] == [1, 2]


class TestConfigRoundTrip:
    @given(
        banner_count=st.integers(min_value=1, max_value=MAX_BANNERS_PER_LANDING),
        dark=st.booleans(),
        presentation=st.sampled_from(["inline", "modal"]),
        band_style=st.sampled_from(["gradient", "solid"]),
        offer_count=st.integers(min_value=1, max_value=3),
    )
    def test_after_every_survives_a_round_trip(
        self,
        banner_count: int,
        dark: bool,
        presentation: str,
        band_style: str,
        offer_count: int,
    ) -> None:
        row = landing_row(
            ctaMode="after_every",
            formPresentation=presentation,
            ctaBandStyle=band_style,
            blocksDarkMode=dark,
            offerCount=offer_count,
        )
        parsed = parse_template_config(snapshot_config(row), banner_count=banner_count)

        assert parsed["cta_mode"] == "after_every"
        assert parsed["form_presentation"] == presentation
        assert parsed["cta_band_style"] == band_style
        assert parsed["blocks_dark_mode"] is dark
        assert parsed["offer_count"] == offer_count
        assert len(parsed["offers"]) == offer_count

    @given(
        banner_count=st.integers(min_value=1, max_value=MAX_BANNERS_PER_LANDING),
        interval=st.integers(min_value=1, max_value=15),
    )
    def test_every_n_survives_a_round_trip(self, banner_count: int, interval: int) -> None:
        row = landing_row(ctaMode="every_n", ctaInterval=interval)
        parsed = parse_template_config(snapshot_config(row), banner_count=banner_count)
        assert parsed["cta_mode"] == "every_n"
        assert parsed["cta_interval"] == interval

    def test_fixed_positions_survive_a_round_trip(self) -> None:
        row = landing_row(ctaMode="fixed_positions", ctaPositions=[1, 3])
        parsed = parse_template_config(snapshot_config(row), banner_count=3)
        assert parsed["cta_mode"] == "fixed_positions"
        assert parsed["cta_positions"] == [1, 3]

    def test_fixed_positions_beyond_the_target_sequence_are_rejected(self) -> None:
        """The load gate makes this unreachable in practice; a corrupt template
        must still fail loudly rather than write positions off the end."""
        stored = snapshot_config(landing_row(ctaMode="fixed_positions", ctaPositions=[1, 9]))
        with pytest.raises(LandingValidationError) as excinfo:
            parse_template_config(stored, banner_count=3)
        assert excinfo.value.field == "cta_positions"

    def test_blank_nullable_text_collapses_to_none(self) -> None:
        parsed = parse_template_config(
            {**snapshot_config(landing_row()), "cta_text": "   ", "form_accent_color": ""},
            banner_count=2,
        )
        assert parsed["cta_text"] is None
        assert parsed["form_accent_color"] is None

    def test_unknown_animation_is_rejected(self) -> None:
        stored = {**snapshot_config(landing_row()), "cta_animation": "explode"}
        with pytest.raises(LandingValidationError) as excinfo:
            parse_template_config(stored, banner_count=2)
        assert excinfo.value.field == "cta_animation"

    @pytest.mark.parametrize("raw", [None, [], "config", 5])
    def test_non_object_config_is_rejected(self, raw: object) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            parse_template_config(raw, banner_count=2)
        assert excinfo.value.field == "config"

    def test_missing_cta_mode_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            parse_template_config({}, banner_count=2)
        assert excinfo.value.field == "cta_mode"


class TestBlockSnapshot:
    def test_snapshot_drops_database_ids_and_keeps_placement(self) -> None:
        payload = snapshot_blocks([block_row(id=999, slotIndex=2, orderIndex=1)])
        assert payload == [
            {
                "block_type": BLOCK_COD_ASSURANCE,
                "slot_index": 2,
                "order_index": 1,
                "config": {"note": "Cobertura nacional"},
                "enabled": True,
            }
        ]
        assert "id" not in payload[0]

    def test_empty_landing_snapshots_an_empty_list(self) -> None:
        assert snapshot_blocks([]) == []

    def test_round_trip_preserves_type_placement_and_enabled_state(self) -> None:
        rows = [
            block_row(slotIndex=0, orderIndex=0, enabled=True),
            block_row(
                blockType=BLOCK_FAQ,
                slotIndex=2,
                orderIndex=0,
                enabled=False,
                config={
                    "title": "Dudas",
                    "items": [{"question": "¿Cuándo?", "answer": "1-3 días"}],
                },
            ),
        ]
        parsed = parse_template_blocks(snapshot_blocks(rows))

        assert [entry["block_type"] for entry in parsed] == [BLOCK_COD_ASSURANCE, BLOCK_FAQ]
        assert [entry["slot_index"] for entry in parsed] == [0, 2]
        assert [entry["enabled"] for entry in parsed] == [True, False]


class TestBlockParsing:
    def test_none_and_empty_mean_no_components(self) -> None:
        assert parse_template_blocks(None) == []
        assert parse_template_blocks([]) == []

    @pytest.mark.parametrize("raw", [{}, "blocks", 5])
    def test_non_list_is_rejected(self, raw: object) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            parse_template_blocks(raw)
        assert excinfo.value.field == "blocks"

    def test_unknown_block_type_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            parse_template_blocks([{"block_type": "countdown", "slot_index": 1, "config": {}}])
        assert excinfo.value.field == "block_type"

    def test_more_components_than_a_landing_allows_is_rejected(self) -> None:
        entries = [
            {"block_type": BLOCK_COD_ASSURANCE, "slot_index": 1, "order_index": index, "config": {}}
            for index in range(MAX_BLOCKS_PER_LANDING + 1)
        ]
        with pytest.raises(LandingValidationError) as excinfo:
            parse_template_blocks(entries)
        assert excinfo.value.field == "blocks"

    def test_colliding_positions_are_separated_rather_than_failing(self) -> None:
        """A corrupt template is recoverable here; the target's unique
        (landing, slot, order) index would otherwise fail mid-write."""
        entries = [
            {"block_type": BLOCK_COD_ASSURANCE, "slot_index": 1, "order_index": 0, "config": {}},
            {"block_type": BLOCK_COD_ASSURANCE, "slot_index": 1, "order_index": 0, "config": {}},
        ]
        parsed = parse_template_blocks(entries)
        positions = {(entry["slot_index"], entry["order_index"]) for entry in parsed}
        assert len(positions) == 2

    def test_out_of_range_order_is_clamped_into_the_column_bound(self) -> None:
        parsed = parse_template_blocks(
            [
                {
                    "block_type": BLOCK_COD_ASSURANCE,
                    "slot_index": 1,
                    "order_index": MAX_ORDER_INDEX + 50,
                    "config": {},
                }
            ]
        )
        assert 0 <= parsed[0]["order_index"] <= MAX_ORDER_INDEX

    def test_invalid_content_for_a_type_is_rejected(self) -> None:
        """`guarantee` requires title and text; a template missing them must
        fail at load rather than create a component that renders nothing."""
        with pytest.raises(LandingValidationError):
            parse_template_blocks(
                [
                    {
                        "block_type": BLOCK_GUARANTEE,
                        "slot_index": 1,
                        "order_index": 0,
                        "config": {"days": 9999},
                    }
                ]
            )
