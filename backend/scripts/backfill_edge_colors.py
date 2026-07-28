"""Backfill precomputed banner edge colors on existing `image_assets` rows.

Edge colors are normally extracted during upload, from the image already in
memory (`app.domains.images.edge_color`). Assets created before that column
existed have none, so their CTA bands fall back to the client neutral. This
script fills them in by re-reading each source object from R2 once.

Read-repair only: it never re-encodes or re-uploads anything, and it only
touches rows whose edge colors are still unset unless `--force` is passed.

Usage (PowerShell), against the settings already in `backend/.env`:

    python -m scripts.backfill_edge_colors --dry-run
    python -m scripts.backfill_edge_colors --limit 200
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys

from app.core.settings import get_settings
from app.db.client import connect_db, disconnect_db, get_db
from app.domains.images.edge_color import extract_edge_colors
from app.storage.r2_client import R2Client, create_r2_client
from PIL import Image


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill banner edge colors.")
    parser.add_argument(
        "--limit", type=int, default=500, help="Maximum assets to process in one run."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute assets that already have edge colors.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing.",
    )
    return parser.parse_args(argv)


async def backfill_edge_colors(
    *, limit: int = 500, force: bool = False, dry_run: bool = False
) -> tuple[int, int]:
    """Fill in missing edge colors; returns `(updated, failed)`."""
    settings = get_settings()
    r2 = R2Client(create_r2_client(settings), bucket=settings.r2_bucket)

    await connect_db()
    db = get_db()
    try:
        where = {"status": "complete"} if force else {"status": "complete", "topEdgeColor": None}
        assets = await db.imageasset.find_many(where=where, take=limit, order={"id": "asc"})

        updated = 0
        failed = 0
        for asset in assets:
            try:
                raw_bytes = await r2.get_bytes(asset.sourceObjectKey)
                with Image.open(io.BytesIO(raw_bytes)) as image:
                    image.load()
                    edges = extract_edge_colors(image)
            except Exception as exc:  # noqa: BLE001 - one bad object must not stop the run
                failed += 1
                print(f"asset {asset.id}: failed ({exc.__class__.__name__})", file=sys.stderr)
                continue

            print(
                f"asset {asset.id}: top={edges.top.color} (flat={edges.top.flat}) "
                f"bottom={edges.bottom.color} (flat={edges.bottom.flat})"
            )
            if dry_run:
                continue

            await db.imageasset.update(
                where={"id": asset.id},
                data={
                    "topEdgeColor": edges.top.color,
                    "bottomEdgeColor": edges.bottom.color,
                    "topEdgeFlat": edges.top.flat,
                    "bottomEdgeFlat": edges.bottom.flat,
                },
            )
            updated += 1

        return updated, failed
    finally:
        await disconnect_db()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.limit <= 0:
        print("--limit must be positive.", file=sys.stderr)
        return 2

    updated, failed = asyncio.run(
        backfill_edge_colors(limit=args.limit, force=args.force, dry_run=args.dry_run)
    )
    verb = "would update" if args.dry_run else "updated"
    print(f"{verb} {updated} asset(s); {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
