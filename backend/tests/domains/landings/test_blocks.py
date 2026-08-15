"""Conversion component vocabulary, slot placement, and content validation
(Requirements 3.27-3.31).

Property under test, in the spirit of the suite's other placement properties:
for any block type in the vocabulary and any content, `validate_block_config`
either raises a field-specific `LandingValidationError` or returns a dict whose
keys are exactly that type's supported content keys — never a presentation key,
and never a value outside the documented bounds.
"""

from __future__ import annotations

import pytest
from app.domains.landings.blocks import (
    ALLOWED_BLOCK_TYPES,
    BLOCK_ANNOUNCEMENT_BAR,
    BLOCK_AUDIENCE,
    BLOCK_BENEFITS,
    BLOCK_COD_ASSURANCE,
    BLOCK_FAQ,
    BLOCK_GUARANTEE,
    BLOCK_HOW_IT_WORKS,
    BLOCK_INCLUDED_BENEFITS,
    BLOCK_MAIN_PROBLEM,
    BLOCK_MOMENT,
    BLOCK_OFFER_PRICE,
    BLOCK_REVIEWS,
    BLOCK_SOLUTION_PRESENTATION,
    MAX_BLOCKS_PER_LANDING,
    MAX_SLOT_INDEX,
    slot_labels,
    validate_block_config,
    validate_block_type,
    validate_can_add_block,
    validate_order_index,
    validate_slot_index,
)
from app.domains.landings.errors import LandingValidationError
from hypothesis import given
from hypothesis import strategies as st

SUPPORTED_KEYS = {
    BLOCK_ANNOUNCEMENT_BAR: {"text", "accent_color", "dark_mode"},
    BLOCK_COD_ASSURANCE: {"note", "accent_color", "dark_mode"},
    BLOCK_BENEFITS: {"title", "items", "accent_color", "dark_mode"},
    BLOCK_OFFER_PRICE: {"compare_at_price", "note", "accent_color", "dark_mode"},
    BLOCK_INCLUDED_BENEFITS: {"title", "items", "accent_color", "dark_mode"},
    BLOCK_REVIEWS: {"title", "items", "accent_color", "dark_mode"},
    BLOCK_FAQ: {"title", "items", "accent_color", "dark_mode"},
    BLOCK_GUARANTEE: {"title", "text", "days", "eyebrow", "benefits", "accent_color", "dark_mode"},
    BLOCK_MAIN_PROBLEM: {
        "eyebrow",
        "title",
        "highlight",
        "subtitle",
        "items",
        "accent_color",
        "dark_mode",
    },
    BLOCK_SOLUTION_PRESENTATION: {
        "bridge_text",
        "eyebrow",
        "title",
        "highlight",
        "text",
        "supporting_text",
        "items",
        "final_title",
        "final_highlight",
        "accent_color",
        "dark_mode",
    },
    BLOCK_HOW_IT_WORKS: {"title", "highlight", "subtitle", "steps", "accent_color", "dark_mode"},
    BLOCK_AUDIENCE: {
        "title",
        "highlight",
        "positive_title",
        "positive_subtitle",
        "positive_items",
        "negative_title",
        "negative_subtitle",
        "negative_items",
        "footer",
        "accent_color",
        "dark_mode",
    },
    BLOCK_MOMENT: {"title", "highlight", "text", "emphasis", "footer", "accent_color", "dark_mode"},
}


class TestVocabulary:
    def test_every_type_has_a_validator_and_key_set(self) -> None:
        assert set(SUPPORTED_KEYS) == set(ALLOWED_BLOCK_TYPES)

    def test_thirteen_types_exist(self) -> None:
        assert len(ALLOWED_BLOCK_TYPES) == 13

    @pytest.mark.parametrize("block_type", ALLOWED_BLOCK_TYPES)
    def test_known_type_is_accepted(self, block_type: str) -> None:
        assert validate_block_type(block_type) == block_type

    @pytest.mark.parametrize("unknown", ["countdown", "stock_counter", "", "COD_ASSURANCE"])
    def test_unknown_type_is_rejected_with_its_field(self, unknown: str) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_block_type(unknown)
        assert excinfo.value.field == "block_type"


class TestSlotBounds:
    @given(slot=st.integers(min_value=0, max_value=MAX_SLOT_INDEX))
    def test_slot_inside_the_sequence_is_accepted(self, slot: int) -> None:
        assert validate_slot_index(slot) == slot

    @given(slot=st.integers(min_value=MAX_SLOT_INDEX + 1, max_value=MAX_SLOT_INDEX + 500))
    def test_slot_past_the_longest_sequence_is_rejected(self, slot: int) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_slot_index(slot)
        assert excinfo.value.field == "slot_index"

    @given(slot=st.integers(min_value=-500, max_value=-1))
    def test_negative_slot_is_rejected(self, slot: int) -> None:
        with pytest.raises(LandingValidationError):
            validate_slot_index(slot)

    def test_booleans_are_not_slots(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_slot_index(True)  # noqa: FBT003 (the point of the test)

    def test_order_index_bounds(self) -> None:
        assert validate_order_index(0) == 0
        with pytest.raises(LandingValidationError) as excinfo:
            validate_order_index(10)
        assert excinfo.value.field == "order_index"

    def test_block_limit_is_enforced(self) -> None:
        validate_can_add_block(MAX_BLOCKS_PER_LANDING - 1)
        with pytest.raises(LandingValidationError):
            validate_can_add_block(MAX_BLOCKS_PER_LANDING)


class TestSlotLabels:
    def test_three_banners_with_a_cta_after_each_offer_seven_slots(self) -> None:
        """3 banners + 3 CTAs is 6 rendered elements, so 7 placement slots:
        one above the sequence and one after each element."""
        labels = slot_labels(3, [1, 2, 3])
        assert len(labels) == 7
        assert labels[1].startswith("1-2")
        assert "banner 1" in labels[1] and "CTA 1" in labels[1]
        assert labels[2].startswith("2-3")
        assert "CTA 1" in labels[2] and "banner 2" in labels[2]
        assert labels[6].startswith("6-7")
        assert "el final" in labels[6]

    def test_a_trailing_cta_is_counted_when_the_last_banner_has_no_position(self) -> None:
        """The page appends a CTA after the last banner when the last position
        is not a CTA position, so that element occupies a slot boundary too."""
        labels = slot_labels(2, [1])
        # banner 1, CTA 1, banner 2, CTA 2 -> 4 elements -> 5 slots
        assert len(labels) == 5
        assert "CTA 2" in labels[3]

    def test_no_banners_still_offers_the_leading_slot(self) -> None:
        assert len(slot_labels(0, [])) == 1

    @given(
        banner_count=st.integers(min_value=0, max_value=15),
        positions=st.lists(st.integers(min_value=1, max_value=15), max_size=15, unique=True),
    )
    def test_slot_count_never_exceeds_the_stored_bound(
        self, banner_count: int, positions: list[int]
    ) -> None:
        """Every slot a landing can offer is a slot `validate_slot_index`
        accepts, so the dashboard can never present a position the API rejects.
        """
        labels = slot_labels(banner_count, positions)
        assert len(labels) - 1 <= MAX_SLOT_INDEX
        for index in range(len(labels)):
            assert validate_slot_index(index) == index


class TestContentValidation:
    def test_announcement_bar_requires_text(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_block_config(BLOCK_ANNOUNCEMENT_BAR, {})
        assert excinfo.value.field == "text"

        result = validate_block_config(BLOCK_ANNOUNCEMENT_BAR, {"text": "  Envío gratis  "})
        assert result == {"text": "Envío gratis", "accent_color": None, "dark_mode": None}

    def test_cod_assurance_needs_no_content(self) -> None:
        assert validate_block_config(BLOCK_COD_ASSURANCE, {}) == {
            "note": None,
            "accent_color": None,
            "dark_mode": None,
        }

    def test_cod_assurance_keeps_only_its_note(self) -> None:
        result = validate_block_config(
            BLOCK_COD_ASSURANCE, {"note": "  Envío a todo el país  ", "padding": "40px"}
        )
        assert result == {"note": "Envío a todo el país", "accent_color": None, "dark_mode": None}

    @pytest.mark.parametrize(
        ("block_type", "config"),
        [
            (BLOCK_BENEFITS, {"items": ["Uno", "Dos"], "background": "#ff0000"}),
            (BLOCK_OFFER_PRICE, {"compare_at_price": 120000, "font_size": "2rem"}),
            (BLOCK_INCLUDED_BENEFITS, {"items": [{"name": "a"}, {"name": "b"}], "margin": 20}),
            (BLOCK_REVIEWS, {"items": [{"name": "Ana", "text": "Buen producto"}], "color": "red"}),
            (
                BLOCK_FAQ,
                {"items": [{"question": "¿Cuándo llega?", "answer": "2 días"}], "css": "x"},
            ),
            (BLOCK_GUARANTEE, {"title": "Garantía", "text": "30 días", "border_radius": 99}),
        ],
    )
    def test_presentation_keys_are_never_stored(self, block_type: str, config: dict) -> None:
        """Spacing/type are decided by the Landing chrome, so a client that
        sends a presentation key gets it dropped rather than persisted. Color
        is the one exception (`accent_color`, tested separately below)."""
        result = validate_block_config(block_type, config)
        assert set(result).issubset(SUPPORTED_KEYS[block_type])
        for presentation_key in ("background", "font_size", "margin", "color", "css", "padding"):
            assert presentation_key not in result

    def test_accent_color_defaults_to_none_on_every_type(self) -> None:
        """Absent `accent_color` means "inherit the form accent" — every type
        accepts the key, and every type is valid without it."""
        minimal_config = {
            BLOCK_ANNOUNCEMENT_BAR: {"text": "Envío gratis"},
            BLOCK_COD_ASSURANCE: {},
            BLOCK_BENEFITS: {"items": ["a", "b"]},
            BLOCK_OFFER_PRICE: {},
            BLOCK_INCLUDED_BENEFITS: {"items": [{"name": "a"}, {"name": "b"}]},
            BLOCK_REVIEWS: {"items": [{"name": "Ana", "text": "ok"}]},
            BLOCK_FAQ: {"items": [{"question": "¿Y?", "answer": "Así."}]},
            BLOCK_GUARANTEE: {"title": "G", "text": "T"},
            BLOCK_MAIN_PROBLEM: {"title": "Problema", "items": [{"title": "Uno", "text": "Texto"}]},
            BLOCK_SOLUTION_PRESENTATION: {
                "title": "Solución",
                "text": "Texto",
                "items": [{"title": "Pilar", "text": "Texto"}],
            },
            BLOCK_HOW_IT_WORKS: {"title": "Cómo", "steps": [{"title": "Paso", "text": "Texto"}]},
            BLOCK_AUDIENCE: {
                "title": "Para quién",
                "positive_title": "Sí",
                "positive_items": ["Uno"],
                "negative_title": "No",
                "negative_items": ["Dos"],
            },
            BLOCK_MOMENT: {"title": "Ahora", "highlight": "Empieza", "text": "Texto"},
        }
        for block_type, config in minimal_config.items():
            result = validate_block_config(block_type, config)
            assert result["accent_color"] is None

    def test_dark_mode_is_tri_state_so_blocks_inherit_by_default(self) -> None:
        assert validate_block_config(BLOCK_COD_ASSURANCE, {})["dark_mode"] is None
        assert validate_block_config(BLOCK_COD_ASSURANCE, {"dark_mode": ""})["dark_mode"] is None
        assert validate_block_config(BLOCK_COD_ASSURANCE, {"dark_mode": True})["dark_mode"] is True
        assert (
            validate_block_config(BLOCK_COD_ASSURANCE, {"dark_mode": False})["dark_mode"] is False
        )

        with pytest.raises(LandingValidationError) as excinfo:
            validate_block_config(BLOCK_COD_ASSURANCE, {"dark_mode": "sometimes"})
        assert excinfo.value.field == "dark_mode"

    @pytest.mark.parametrize("block_type", ALLOWED_BLOCK_TYPES)
    def test_accent_color_is_normalized_like_any_other_accent(self, block_type: str) -> None:
        base_config = {
            BLOCK_ANNOUNCEMENT_BAR: {"text": "Envío gratis"},
            BLOCK_COD_ASSURANCE: {},
            BLOCK_BENEFITS: {"items": ["a", "b"]},
            BLOCK_OFFER_PRICE: {},
            BLOCK_INCLUDED_BENEFITS: {"items": [{"name": "a"}, {"name": "b"}]},
            BLOCK_REVIEWS: {"items": [{"name": "Ana", "text": "ok"}]},
            BLOCK_FAQ: {"items": [{"question": "¿Y?", "answer": "Así."}]},
            BLOCK_GUARANTEE: {"title": "G", "text": "T"},
            BLOCK_MAIN_PROBLEM: {"title": "Problema", "items": [{"title": "Uno", "text": "Texto"}]},
            BLOCK_SOLUTION_PRESENTATION: {
                "title": "Solución",
                "text": "Texto",
                "items": [{"title": "Pilar", "text": "Texto"}],
            },
            BLOCK_HOW_IT_WORKS: {"title": "Cómo", "steps": [{"title": "Paso", "text": "Texto"}]},
            BLOCK_AUDIENCE: {
                "title": "Para quién",
                "positive_title": "Sí",
                "positive_items": ["Uno"],
                "negative_title": "No",
                "negative_items": ["Dos"],
            },
            BLOCK_MOMENT: {"title": "Ahora", "highlight": "Empieza", "text": "Texto"},
        }[block_type]
        result = validate_block_config(block_type, {**base_config, "accent_color": "#ABC"})
        assert result["accent_color"] == "#aabbcc"

    @pytest.mark.parametrize("block_type", ALLOWED_BLOCK_TYPES)
    def test_malformed_accent_color_is_rejected_with_its_field(self, block_type: str) -> None:
        base_config = {
            BLOCK_ANNOUNCEMENT_BAR: {"text": "Envío gratis"},
            BLOCK_COD_ASSURANCE: {},
            BLOCK_BENEFITS: {"items": ["a", "b"]},
            BLOCK_OFFER_PRICE: {},
            BLOCK_INCLUDED_BENEFITS: {"items": [{"name": "a"}, {"name": "b"}]},
            BLOCK_REVIEWS: {"items": [{"name": "Ana", "text": "ok"}]},
            BLOCK_FAQ: {"items": [{"question": "¿Y?", "answer": "Así."}]},
            BLOCK_GUARANTEE: {"title": "G", "text": "T"},
            BLOCK_MAIN_PROBLEM: {"title": "Problema", "items": [{"title": "Uno", "text": "Texto"}]},
            BLOCK_SOLUTION_PRESENTATION: {
                "title": "Solución",
                "text": "Texto",
                "items": [{"title": "Pilar", "text": "Texto"}],
            },
            BLOCK_HOW_IT_WORKS: {"title": "Cómo", "steps": [{"title": "Paso", "text": "Texto"}]},
            BLOCK_AUDIENCE: {
                "title": "Para quién",
                "positive_title": "Sí",
                "positive_items": ["Uno"],
                "negative_title": "No",
                "negative_items": ["Dos"],
            },
            BLOCK_MOMENT: {"title": "Ahora", "highlight": "Empieza", "text": "Texto"},
        }[block_type]
        with pytest.raises(LandingValidationError) as excinfo:
            validate_block_config(block_type, {**base_config, "accent_color": "not-a-color"})
        assert excinfo.value.field == "accent_color"

    def test_benefits_bounds(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_block_config(BLOCK_BENEFITS, {"items": ["solo uno"]})
        assert excinfo.value.field == "items"

        with pytest.raises(LandingValidationError):
            validate_block_config(BLOCK_BENEFITS, {"items": ["a", "b", "c", "d", "e", "f"]})

        assert validate_block_config(BLOCK_BENEFITS, {"items": [" a ", "b"]})["items"] == ["a", "b"]

    def test_benefit_length_is_bounded(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_block_config(BLOCK_BENEFITS, {"items": ["x" * 200, "ok"]})

    def test_offer_price_rejects_non_numeric_and_non_positive_reference(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_block_config(BLOCK_OFFER_PRICE, {"compare_at_price": "gratis"})
        assert excinfo.value.field == "compare_at_price"

        with pytest.raises(LandingValidationError):
            validate_block_config(BLOCK_OFFER_PRICE, {"compare_at_price": 0})

    def test_offer_price_accepts_an_absent_reference(self) -> None:
        assert validate_block_config(BLOCK_OFFER_PRICE, {}) == {
            "compare_at_price": None,
            "note": None,
            "accent_color": None,
            "dark_mode": None,
        }

    def test_included_benefits_requires_between_2_and_8_items(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_block_config(BLOCK_INCLUDED_BENEFITS, {"items": [{"name": "solo uno"}]})
        assert excinfo.value.field == "items"

        valid = validate_block_config(
            BLOCK_INCLUDED_BENEFITS, {"items": [{"name": "a"}, {"name": "b"}]}
        )
        assert len(valid["items"]) == 2

    def test_included_benefits_item_requires_name(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_block_config(
                BLOCK_INCLUDED_BENEFITS, {"items": [{"value": "x"}, {"name": "b"}]}
            )
        assert excinfo.value.field == "items"

    def test_included_benefits_item_optional_fields(self) -> None:
        result = validate_block_config(
            BLOCK_INCLUDED_BENEFITS,
            {
                "items": [
                    {"name": "Curso completo", "value": "Valor USD 497", "tag": "GRATIS"},
                    {"name": "Guía PDF"},
                ]
            },
        )
        assert result["items"][0]["name"] == "Curso completo"
        assert result["items"][0]["value"] == "Valor USD 497"
        assert result["items"][0]["tag"] == "GRATIS"
        assert result["items"][1]["value"] is None
        assert result["items"][1]["tag"] is None

    def test_review_rating_is_bounded_and_optional(self) -> None:
        result = validate_block_config(
            BLOCK_REVIEWS,
            {"items": [{"name": "Ana", "city": "Cali", "text": "Llegó rápido", "rating": 5}]},
        )
        assert result["items"][0]["rating"] == 5

        with pytest.raises(LandingValidationError):
            validate_block_config(
                BLOCK_REVIEWS, {"items": [{"name": "Ana", "text": "ok", "rating": 9}]}
            )

        no_rating = validate_block_config(BLOCK_REVIEWS, {"items": [{"name": "Ana", "text": "ok"}]})
        assert no_rating["items"][0]["rating"] is None

    def test_reviews_require_name_and_text(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_block_config(BLOCK_REVIEWS, {"items": [{"name": "Ana"}]})
        with pytest.raises(LandingValidationError):
            validate_block_config(BLOCK_REVIEWS, {"items": [{"text": "solo texto"}]})

    def test_faq_requires_question_and_answer_and_caps_the_list(self) -> None:
        with pytest.raises(LandingValidationError):
            validate_block_config(BLOCK_FAQ, {"items": [{"question": "¿Y?"}]})

        with pytest.raises(LandingValidationError):
            validate_block_config(
                BLOCK_FAQ,
                {"items": [{"question": f"q{i}", "answer": "a"} for i in range(7)]},
            )

    def test_guarantee_requires_title_and_text(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_block_config(BLOCK_GUARANTEE, {"text": "sin título"})
        assert excinfo.value.field == "title"

        result = validate_block_config(
            BLOCK_GUARANTEE, {"title": "Garantía", "text": "Devolución", "days": "30"}
        )
        assert result["days"] == 30

    def test_guarantee_days_are_bounded(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_block_config(BLOCK_GUARANTEE, {"title": "G", "text": "T", "days": 4000})
        assert excinfo.value.field == "days"

    def test_story_blocks_normalize_repeated_content(self) -> None:
        problem = validate_block_config(
            BLOCK_MAIN_PROBLEM,
            {"title": " Problema ", "items": [{"title": " Uno ", "text": " Texto "}]},
        )
        assert problem["title"] == "Problema"
        assert problem["items"][0] == {"title": "Uno", "text": "Texto"}

        steps = validate_block_config(
            BLOCK_HOW_IT_WORKS,
            {"title": "Cómo", "steps": [{"kicker": "Día 1", "title": "Uno", "text": "Hazlo"}]},
        )
        assert steps["steps"][0]["kicker"] == "Día 1"

    def test_audience_requires_both_lists(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_block_config(
                BLOCK_AUDIENCE,
                {
                    "title": "Para quién",
                    "positive_title": "Sí",
                    "positive_items": ["Uno"],
                    "negative_title": "No",
                    "negative_items": [],
                },
            )
        assert excinfo.value.field == "negative_items"

    def test_solution_final_title_is_optional(self) -> None:
        result = validate_block_config(
            BLOCK_SOLUTION_PRESENTATION,
            {
                "title": "Solución",
                "text": "Descripción",
                "items": [{"title": "Pilar", "text": "Contenido"}],
            },
        )
        assert result["final_title"] is None
        assert result["final_highlight"] is None

    def test_rich_guarantee_accepts_benefit_cards(self) -> None:
        result = validate_block_config(
            BLOCK_GUARANTEE,
            {
                "title": "Garantía",
                "text": "Compra protegida",
                "days": 7,
                "benefits": [{"title": "Riesgo cero", "text": "Protegida"}],
            },
        )
        assert result["benefits"][0]["title"] == "Riesgo cero"

    def test_non_object_config_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError) as excinfo:
            validate_block_config(BLOCK_BENEFITS, ["not", "an", "object"])
        assert excinfo.value.field == "config"

    @given(
        block_type=st.sampled_from(ALLOWED_BLOCK_TYPES),
        config=st.dictionaries(
            keys=st.sampled_from(
                [
                    "note",
                    "title",
                    "items",
                    "steps",
                    "text",
                    "days",
                    "compare_at_price",
                    "padding",
                    "accent_color",
                ]
            ),
            values=st.one_of(
                st.none(),
                st.booleans(),
                st.integers(min_value=-1000, max_value=1000),
                st.text(max_size=30),
                st.lists(st.text(max_size=30), max_size=8),
            ),
            max_size=5,
        ),
    )
    def test_validation_either_raises_a_field_error_or_returns_supported_keys(
        self, block_type: str, config: dict
    ) -> None:
        try:
            result = validate_block_config(block_type, config)
        except LandingValidationError as exc:
            assert exc.field
            assert exc.message
        else:
            assert set(result) == SUPPORTED_KEYS[block_type]
