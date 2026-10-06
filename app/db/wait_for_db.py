import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    url = os.environ.get("DATABASE_URL", "")
    for _ in range(30):
        try:
            engine = create_async_engine(url)
            async with engine.connect() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            await engine.dispose()
            print("Database is ready")
            return
        except Exception:
            await asyncio.sleep(2)
    print("Database not ready", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
