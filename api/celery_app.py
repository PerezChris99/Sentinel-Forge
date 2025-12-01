"""
Celery configuration for background tasks.
"""
import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "sentinelforge",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Periodic tasks schedule
celery_app.conf.beat_schedule = {
    "purge-old-unknowns": {
        "task": "api.tasks.purge_old_unknowns",
        "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
    },
}

celery_app.autodiscover_tasks(["api"])
