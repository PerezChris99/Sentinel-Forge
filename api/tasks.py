"""
Celery background tasks for SentinelForge.
"""
from datetime import datetime, timedelta
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from api.celery_app import celery_app
from api.runtime import load_config
from db.models import Sighting

DB_URL = load_config().db_url


@celery_app.task(name="api.tasks.purge_old_unknowns")
def purge_old_unknowns():
    """
    Delete unknown sightings older than 90 days (TTL purge for privacy).
    """
    import asyncio
    
    async def _purge():
        engine = create_async_engine(DB_URL)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as session:
            cutoff = datetime.utcnow() - timedelta(days=90)
            stmt = delete(Sighting).where(
                Sighting.person_id.is_(None),
                Sighting.timestamp < cutoff
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
    
    deleted = asyncio.run(_purge())
    return {"deleted": deleted}
