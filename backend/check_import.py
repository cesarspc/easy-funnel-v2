import traceback
import asyncio
import os

os.environ.setdefault("DATABASE_URL", "postgresql://cod_user:cod_password@localhost:55432/cod_platform_test")

async def main():
    try:
        from prisma import Prisma
        db = Prisma()
        await db.connect()
        landing = await db.landing.find_first(where={"id": 1})
        if landing:
            print(f"Landing found: {landing.slug}")
            print(f"Has blocksDarkMode attr: {hasattr(landing, 'blocksDarkMode')}")
            if hasattr(landing, 'blocksDarkMode'):
                print(f"blocksDarkMode value: {landing.blocksDarkMode}")
            else:
                print("MISSING blocksDarkMode - Prisma client not regenerated properly")
                print(f"Available attrs: {[a for a in dir(landing) if not a.startswith('_') and 'dark' in a.lower()]}")
        else:
            print("No landing with id=1")
        await db.disconnect()
    except Exception as e:
        traceback.print_exc()
        print(f"\nERROR: {e}")

asyncio.run(main())
