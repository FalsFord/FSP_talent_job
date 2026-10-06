import asyncio

from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine
from app.models import *  # noqa: F401, F403


async def init() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init())
