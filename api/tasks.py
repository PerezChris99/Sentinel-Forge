"""
Celery background tasks for SentinelForge.
"""
from datetime import datetime, timedelta
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
import os

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


@celery_app.task(name="api.tasks.send_alfie_webhook")
def send_alfie_webhook(payload: dict):
    """
    Send webhook to ALFIE for high-risk alerts.
    """
    import requests
    
    alfie_url = os.getenv("ALFIE_WEBHOOK_URL")
    if not alfie_url:
        return {"status": "skipped", "reason": "ALFIE_WEBHOOK_URL not configured"}
    
    try:
        response = requests.post(alfie_url, json=payload, timeout=5)
        response.raise_for_status()
        return {"status": "success", "response": response.json()}
    except Exception as e:
        return {"status": "error", "error": str(e)}
