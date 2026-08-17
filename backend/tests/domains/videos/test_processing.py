"""Bounded, single-output video normalization."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.domains.videos import processing
from app.domains.videos.processing import VideoValidationError


def test_rejects_empty_and_oversized_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(VideoValidationError) as empty:
        processing.optimize_video(b"")
    assert empty.value.field == "file"

    monkeypatch.setattr(processing, "SOURCE_VIDEO_MAX_BYTES", 4)
    with pytest.raises(VideoValidationError) as oversized:
        processing.optimize_video(b"12345")
    assert oversized.value.field == "file"


def test_emits_one_faststart_mp4_and_one_webp_poster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes = iter([(1080, 1920, 30.0), (720, 1280, 30.0)])
    commands: list[list[str]] = []
    monkeypatch.setattr(processing, "_probe", lambda _path: next(probes))

    def fake_run(command: list[str]):  # type: ignore[no-untyped-def]
        commands.append(command)
        destination = Path(command[-1])
        destination.write_bytes(b"poster" if destination.suffix == ".webp" else b"mp4")
        return None

    monkeypatch.setattr(processing, "_run", fake_run)

    result = processing.optimize_video(b"source")

    assert result.video == b"mp4"
    assert result.poster == b"poster"
    assert (result.width, result.height, result.duration_ms) == (720, 1280, 30_000)
    assert len(commands) == 2
    assert "+faststart" in commands[0]
    assert "libx264" in commands[0]
    assert commands[0][commands[0].index("-maxrate") + 1] == "900k"
    assert commands[0][commands[0].index("-bufsize") + 1] == "1800k"
    assert commands[0][commands[0].index("-r") + 1] == "30"
    assert commands[1][commands[1].index("-q:v") + 1] == "72"


def test_rejects_video_longer_than_ninety_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(processing, "_probe", lambda _path: (720, 1280, 90.01))
    with pytest.raises(VideoValidationError) as excinfo:
        processing.optimize_video(b"source")
    assert "90" in excinfo.value.message
