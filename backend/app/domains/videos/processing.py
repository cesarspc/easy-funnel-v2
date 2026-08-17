"""FFmpeg-backed, single-variant video normalization.

Only the optimized MP4 and one WebP poster leave this module; source uploads
exist in a temporary directory for the duration of the request and are never
stored in R2.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

SOURCE_VIDEO_MAX_BYTES = 100 * 1024 * 1024
MAX_DURATION_SECONDS = 90.0
MAX_SOURCE_DIMENSION = 4096


class VideoValidationError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class VideoPipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class OptimizedVideo:
    video: bytes
    poster: bytes
    width: int
    height: int
    duration_ms: int


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError as exc:
        raise VideoPipelineError("FFmpeg is unavailable.") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise VideoPipelineError("Video processing failed.") from exc


def _probe(path: Path) -> tuple[int, int, float]:
    try:
        result = _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:format=duration",
                "-of",
                "json",
                str(path),
            ]
        )
    except VideoPipelineError as exc:
        if isinstance(exc.__cause__, FileNotFoundError):
            raise
        raise VideoValidationError("file", "El archivo no contiene un video válido.") from exc
    try:
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
        return int(stream["width"]), int(stream["height"]), float(payload["format"]["duration"])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise VideoValidationError("file", "El archivo no contiene un video válido.") from exc


def optimize_video(raw_bytes: bytes) -> OptimizedVideo:
    if not raw_bytes:
        raise VideoValidationError("file", "Selecciona un video.")
    if len(raw_bytes) > SOURCE_VIDEO_MAX_BYTES:
        raise VideoValidationError("file", "El video supera el máximo de 100 MB.")

    with tempfile.TemporaryDirectory(prefix="easy-funnel-video-") as temp_dir:
        root = Path(temp_dir)
        source = root / "source"
        output = root / "video.mp4"
        poster = root / "poster.webp"
        source.write_bytes(raw_bytes)

        width, height, duration = _probe(source)
        if width < 1 or height < 1 or max(width, height) > MAX_SOURCE_DIMENSION:
            raise VideoValidationError("file", "La resolución máxima permitida es 4096 px.")
        if duration <= 0 or duration > MAX_DURATION_SECONDS:
            raise VideoValidationError("file", "El video debe durar máximo 90 segundos.")

        # Cap inside 720x1280, preserve aspect ratio and force even dimensions
        # required by yuv420p. faststart moves the MP4 index to the beginning.
        scale = (
            "scale='min(720,iw)':'min(1280,ih)':"
            "force_original_aspect_ratio=decrease:force_divisible_by=2"
        )
        _run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-vf",
                scale,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "28",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-ac",
                "2",
                "-y",
                str(output),
            ]
        )
        _run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-ss",
                "0.1",
                "-i",
                str(output),
                "-frames:v",
                "1",
                "-vf",
                "scale='min(720,iw)':-2",
                "-q:v",
                "72",
                "-y",
                str(poster),
            ]
        )
        out_width, out_height, out_duration = _probe(output)
        return OptimizedVideo(
            video=output.read_bytes(),
            poster=poster.read_bytes(),
            width=out_width,
            height=out_height,
            duration_ms=max(1, round(out_duration * 1000)),
        )
