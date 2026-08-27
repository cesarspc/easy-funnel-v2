"""Contract validation for bulk creation from Landing templates."""

from __future__ import annotations

import pytest
from app.domains.landings.errors import LandingValidationError
from app.domains.landings.template_instantiation import (
    describe_media_requirements,
    r2_original_object_key,
    validate_block_asset_assignments,
)


class TestR2OriginalObjectKey:
    @pytest.mark.parametrize(
        ("url", "host", "expected"),
        [
            (
                "https://media.example.com/originals/banner.png",
                "https://media.example.com",
                "originals/banner.png",
            ),
            (
                "https://media.example.com/bucket/originals/video.mov",
                "https://media.example.com/bucket",
                "originals/video.mov",
            ),
        ],
    )
    def test_accepts_only_configured_public_host_urls(
        self, url: str, host: str, expected: str
    ) -> None:
        assert r2_original_object_key(url, public_host=host) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "https://attacker.example/originals/banner.png",
            "https://media.example.com/variants/banner/480.webp",
            "https://media.example.com/originals/nested/banner.png",
            "https://media.example.com/originals/../private",
            "https://media.example.com/originals/banner.png?token=secret",
        ],
    )
    def test_rejects_external_or_non_original_paths(self, url: str) -> None:
        with pytest.raises(LandingValidationError) as raised:
            r2_original_object_key(url, public_host="https://media.example.com")
        assert raised.value.field == "original_url"


def _requirements(offer_count: int = 3):
    return describe_media_requirements(
        [
            {"block_type": "announcement_bar"},
            {"block_type": "video_carousel"},
            {"block_type": "offers_price"},
            {"block_type": "offers_price"},
        ],
        offer_count=offer_count,
    )


class TestBlockAssetAssignments:
    def test_each_offer_block_requires_every_visible_quantity(self) -> None:
        assignments = [
            {"block_index": 1, "videos": []},
            {
                "block_index": 2,
                "offer_images": [{"quantity": 1}, {"quantity": 2}, {"quantity": 3}],
            },
            {
                "block_index": 3,
                "offer_images": [{"quantity": 1}, {"quantity": 2}, {"quantity": 3}],
            },
        ]

        validated = validate_block_asset_assignments(_requirements(), assignments)

        assert set(validated) == {1, 2, 3}

    def test_video_block_may_be_omitted_to_mean_zero_videos(self) -> None:
        assignments = [
            {
                "block_index": 2,
                "offer_images": [{"quantity": 1}, {"quantity": 2}],
            },
            {
                "block_index": 3,
                "offer_images": [{"quantity": 1}, {"quantity": 2}],
            },
        ]
        validated = validate_block_asset_assignments(_requirements(2), assignments)
        assert 1 not in validated

    @pytest.mark.parametrize(
        "assignments",
        [
            [{"block_index": 2, "offer_images": [{"quantity": 1}, {"quantity": 2}]}],
            [
                {
                    "block_index": 2,
                    "offer_images": [
                        {"quantity": 1},
                        {"quantity": 2},
                        {"quantity": 2},
                    ],
                },
                {
                    "block_index": 3,
                    "offer_images": [
                        {"quantity": 1},
                        {"quantity": 2},
                        {"quantity": 3},
                    ],
                },
            ],
        ],
    )
    def test_missing_or_duplicate_offer_quantities_are_rejected(self, assignments) -> None:
        with pytest.raises(LandingValidationError) as raised:
            validate_block_asset_assignments(_requirements(), assignments)
        assert raised.value.field == "offer_images"

    def test_each_carousel_accepts_at_most_six_videos(self) -> None:
        assignments = [
            {"block_index": 1, "videos": [{} for _ in range(7)]},
            {
                "block_index": 2,
                "offer_images": [{"quantity": 1}, {"quantity": 2}, {"quantity": 3}],
            },
            {
                "block_index": 3,
                "offer_images": [{"quantity": 1}, {"quantity": 2}, {"quantity": 3}],
            },
        ]
        with pytest.raises(LandingValidationError) as raised:
            validate_block_asset_assignments(_requirements(), assignments)
        assert raised.value.field == "block_assets"
