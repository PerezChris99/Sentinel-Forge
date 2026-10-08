"""
Celery background tasks for SentinelForge.
"""
from datetime import datetime, timedelta
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
import hashlib
import hmac
import json
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


@celery_app.task(name="api.tasks.send_alfie_webhook", bind=True, max_retries=3)
def send_alfie_webhook(self, payload: dict):
    """Send a signed webhook to ALFIE for high-risk alerts."""
    import requests

    alfie_url = os.getenv("ALFIE_WEBHOOK_URL")
    if not alfie_url:
        return {"status": "skipped", "reason": "ALFIE_WEBHOOK_URL not configured"}

    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    headers = {"Content-Type": "application/json", "User-Agent": "SentinelForge/1.0"}
    secret = os.getenv("ALFIE_WEBHOOK_SECRET", "")
    if secret:
        headers["X-SentinelForge-Signature"] = hmac.new(
            secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    try:
        response = requests.post(alfie_url, data=body, headers=headers, timeout=10)
        response.raise_for_status()
        return {"status": "success", "http_status": response.status_code}
    except requests.RequestException as exc:
        raise self.retry(exc=exc, countdown=30)
