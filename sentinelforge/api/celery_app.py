"""
Celery configuration for background tasks.
"""
import os
from datetime import timedelta
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
    # API tasks
    "purge-old-unknowns": {
        "task": "api.tasks.purge_old_unknowns",
        "schedule": crontab(hour=2, minute=0),  # Daily at 02:00 UTC
    },
    
    # Analytics tasks
    "detect-patterns-daily": {
        "task": "analytics.tasks.detect_patterns_task",
        "schedule": crontab(hour=2, minute=30),  # Daily at 02:30 UTC
    },
    "train-anomaly-detector-weekly": {
        "task": "analytics.tasks.train_anomaly_detector_task",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),  # Sunday 03:00 UTC
    },
    "score-recent-sightings": {
        "task": "analytics.tasks.score_recent_sightings_task",
        "schedule": timedelta(hours=6),  # Every 6 hours
    },
    "cluster-unknowns-daily": {
        "task": "analytics.tasks.cluster_unknowns_task",
        "schedule": crontab(hour=4, minute=0),  # Daily at 04:00 UTC
    },
}

celery_app.autodiscover_tasks(["api", "analytics"])
