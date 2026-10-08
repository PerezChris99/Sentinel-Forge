import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from db.models import Base, Person


def test_models_create_on_sqlite():
    async def _run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_run())
