"""Quick check: are the new columns present in the connected database?"""
import asyncio
from prisma import Prisma

async def main():
    db = Prisma()
    await db.connect()
    rows = await db.query_raw(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'landings' "
        "AND column_name IN ('offers', 'offer_count', 'accent_color') "
        "ORDER BY column_name"
    )
    print("Landing columns found:", [r["column_name"] for r in rows])

    rows2 = await db.query_raw(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'orders' "
        "AND column_name IN ('unit_price', 'discount_percent', 'total_price') "
        "ORDER BY column_name"
    )
    print("Order columns found:", [r["column_name"] for r in rows2])
    await db.disconnect()

asyncio.run(main())
