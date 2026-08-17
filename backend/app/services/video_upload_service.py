"""Upload lifecycle for optimized video-carousel assets."""

from __future__ import annotations

import asyncio
import contextlib

from prisma import Prisma

from app.domains.images.opaque_key import generate_opaque_key
from app.domains.landings.errors import LandingNotFoundError, LandingValidationError
from app.domains.videos import (
    OptimizedVideo,
    VideoPipelineError,
    VideoValidationError,
    optimize_video,
)
from app.storage.r2_client import R2Client, video_object_key, video_poster_object_key

MAX_VIDEOS_PER_CAROUSEL = 6


class VideoNotFoundError(LandingValidationError):
    def __init__(self) -> None:
        super().__init__("video_id", "Video not found.")


class VideoUploadService:
    def __init__(self, db: Prisma, r2: R2Client) -> None:
        self._db = db
        self._r2 = r2

    async def upload(
        self,
        landing_id: int,
        block_id: int,
        *,
        raw_bytes: bytes,
        caption: str | None,
        actor: str,
    ) -> None:
        block = await self._db.landingblock.find_first(
            where={"id": block_id, "landingId": landing_id}
        )
        if block is None:
            raise LandingNotFoundError(landing_id)
        if block.blockType != "video_carousel":
            raise LandingValidationError("block_id", "El componente no es un carrusel de videos.")
        existing = await self._db.videoasset.find_many(
            where={"landingBlockId": block_id}, order={"orderIndex": "asc"}
        )
        if len(existing) >= MAX_VIDEOS_PER_CAROUSEL:
            raise LandingValidationError("file", "El carrusel admite máximo 6 videos.")

        clean_caption = caption.strip() if isinstance(caption, str) else ""
        if len(clean_caption) > 100:
            raise LandingValidationError("caption", "El texto no puede superar 100 caracteres.")

        optimized: OptimizedVideo = await asyncio.to_thread(optimize_video, raw_bytes)
        opaque_key = generate_opaque_key()
        video_key = video_object_key(opaque_key)
        poster_key = video_poster_object_key(opaque_key)
        uploaded: list[str] = []
        try:
            await self._r2.put_bytes(video_key, optimized.video, content_type="video/mp4")
            uploaded.append(video_key)
            await self._r2.put_bytes(poster_key, optimized.poster, content_type="image/webp")
            uploaded.append(poster_key)
            async with self._db.tx() as tx:
                asset = await tx.videoasset.create(
                    data={
                        "landingBlockId": block_id,
                        "opaqueKey": opaque_key,
                        "videoObjectKey": video_key,
                        "posterObjectKey": poster_key,
                        "width": optimized.width,
                        "height": optimized.height,
                        "durationMs": optimized.duration_ms,
                        "byteSize": len(optimized.video),
                        "orderIndex": len(existing),
                        "caption": clean_caption or None,
                    }
                )
                await tx.auditlog.create(
                    data={
                        "actor": actor,
                        "action": "video.upload",
                        "targetType": "video_asset",
                        "targetId": str(asset.id),
                        "result": "success",
                    }
                )
        except (LandingValidationError, VideoPipelineError, VideoValidationError):
            raise
        except Exception as exc:
            for key in uploaded:
                with contextlib.suppress(Exception):
                    await self._r2.delete(key)
            raise VideoPipelineError("Video upload failed.") from exc

    async def delete(self, landing_id: int, block_id: int, video_id: int, *, actor: str) -> None:
        block = await self._db.landingblock.find_first(
            where={"id": block_id, "landingId": landing_id}
        )
        if block is None:
            raise VideoNotFoundError()
        asset = await self._db.videoasset.find_first(
            where={"id": video_id, "landingBlockId": block_id}
        )
        if asset is None:
            raise VideoNotFoundError()

        async with self._db.tx() as tx:
            await tx.videoasset.delete(where={"id": video_id})
            remaining = await tx.videoasset.find_many(
                where={"landingBlockId": block_id}, order={"orderIndex": "asc"}
            )
            for index, item in enumerate(remaining):
                if item.orderIndex != index:
                    await tx.videoasset.update(where={"id": item.id}, data={"orderIndex": index})
            await tx.auditlog.create(
                data={
                    "actor": actor,
                    "action": "video.delete",
                    "targetType": "video_asset",
                    "targetId": str(video_id),
                    "result": "success",
                }
            )
        for key in (asset.videoObjectKey, asset.posterObjectKey):
            with contextlib.suppress(Exception):
                await self._r2.delete(key)
