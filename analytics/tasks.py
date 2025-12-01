"""
Celery Beat Schedule for Analytics Tasks
Periodic jobs for pattern detection, anomaly scoring, and model retraining
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.engine import AnalyticsEngine, BiasAuditor
from db.models import Sighting, Pattern, Person
from api.celery_app import celery_app

logger = get_task_logger(__name__)


@shared_task(name="analytics.detect_patterns")
def detect_patterns_task(lookback_days: int = 30):
    """
    Periodic pattern detection task.
    Analyzes sightings and publishes patterns to database.
    
    Schedule: Daily at 02:00 UTC
    """
    import asyncio
    from api.main import async_session_maker
    
    async def _run():
        async with async_session_maker() as session:
            # Fetch recent sightings
            cutoff = datetime.utcnow() - timedelta(days=lookback_days)
            query = select(Sighting).where(Sighting.timestamp >= cutoff)
            result = await session.execute(query)
            sightings = result.scalars().all()
            
            if not sightings:
                logger.info("No sightings to analyze")
                return 0
            
            # Convert to DataFrame
            df = pd.DataFrame([
                {
                    "person_id": str(s.person_id) if s.person_id else None,
                    "timestamp": s.timestamp,
                    "camera_id": s.camera_id,
                    "confidence": s.confidence,
                    "flag_level": s.flag_level
                }
                for s in sightings
            ])
            
            # Run pattern detection
            engine = AnalyticsEngine()
            patterns = engine.detect_patterns(df, lookback_days=lookback_days)
            
            # Save patterns to database
            pattern_count = 0
            for p in patterns:
                pattern = Pattern(
                    person_id=p["person_id"],
                    pattern_type=p["pattern_type"],
                    confidence=p["confidence"],
                    sighting_count=p["sighting_count"],
                    metadata=p["metadata"],
                    detected_at=datetime.utcnow()
                )
                session.add(pattern)
                pattern_count += 1
            
            await session.commit()
            logger.info(f"Detected and saved {pattern_count} patterns")
            return pattern_count
    
    return asyncio.run(_run())


@shared_task(name="analytics.train_anomaly_detector")
def train_anomaly_detector_task(min_samples: int = 100):
    """
    Retrain anomaly detection model on recent embeddings.
    
    Schedule: Weekly on Sunday at 03:00 UTC
    """
    import asyncio
    from api.main import async_session_maker
    
    async def _run():
        async with async_session_maker() as session:
            # Fetch recent known sightings
            cutoff = datetime.utcnow() - timedelta(days=90)
            query = (
                select(Sighting)
                .where(
                    Sighting.timestamp >= cutoff,
                    Sighting.person_id.isnot(None)
                )
                .limit(10000)  # Limit for performance
            )
            result = await session.execute(query)
            sightings = result.scalars().all()
            
            if len(sightings) < min_samples:
                logger.warning(f"Insufficient samples for training: {len(sightings)} < {min_samples}")
                return False
            
            # Extract embeddings
            embeddings = np.array([s.embedding for s in sightings if s.embedding])
            
            # Train model
            engine = AnalyticsEngine(anomaly_contamination=0.1, use_pca=True)
            engine.train_anomaly_detector(embeddings)
            
            # Save model
            model_path = "analytics/models/anomaly_detector.joblib"
            engine.save_model(model_path)
            
            logger.info(f"Anomaly detector retrained on {len(embeddings)} samples")
            return True
    
    return asyncio.run(_run())


@shared_task(name="analytics.score_recent_sightings")
def score_recent_sightings_task(hours: int = 24):
    """
    Calculate anomaly scores for recent sightings.
    
    Schedule: Every 6 hours
    """
    import asyncio
    from api.main import async_session_maker
    
    async def _run():
        async with async_session_maker() as session:
            # Load model
            try:
                engine = AnalyticsEngine()
                engine.load_model("analytics/models/anomaly_detector.joblib")
            except FileNotFoundError:
                logger.warning("No trained model found, skipping scoring")
                return 0
            
            # Fetch recent sightings without scores
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            query = select(Sighting).where(Sighting.timestamp >= cutoff)
            result = await session.execute(query)
            sightings = result.scalars().all()
            
            if not sightings:
                logger.info("No recent sightings to score")
                return 0
            
            # Extract embeddings
            embeddings = np.array([s.embedding for s in sightings if s.embedding])
            
            if len(embeddings) == 0:
                return 0
            
            # Calculate scores
            scores = engine.predict_anomaly_score(embeddings)
            
            # Update database (store in Pattern table as anomaly patterns)
            scored_count = 0
            for sighting, score in zip(sightings, scores):
                if score > 0.7:  # Only store high anomaly scores
                    pattern = Pattern(
                        person_id=sighting.person_id,
                        pattern_type="anomaly",
                        confidence=float(score),
                        sighting_count=1,
                        metadata={"anomaly_score": float(score), "sighting_id": str(sighting.id)},
                        detected_at=datetime.utcnow()
                    )
                    session.add(pattern)
                    scored_count += 1
            
            await session.commit()
            logger.info(f"Scored {len(sightings)} sightings, {scored_count} high-anomaly patterns saved")
            return scored_count
    
    return asyncio.run(_run())


@shared_task(name="analytics.cluster_unknowns")
def cluster_unknowns_task(days: int = 90):
    """
    Cluster unknown faces to identify repeat unknowns.
    
    Schedule: Daily at 04:00 UTC
    """
    import asyncio
    from api.main import async_session_maker
    
    async def _run():
        async with async_session_maker() as session:
            # Fetch unknown sightings
            cutoff = datetime.utcnow() - timedelta(days=days)
            query = (
                select(Sighting)
                .where(
                    Sighting.timestamp >= cutoff,
                    Sighting.person_id.is_(None)
                )
            )
            result = await session.execute(query)
            unknowns = result.scalars().all()
            
            if len(unknowns) < 3:
                logger.info(f"Insufficient unknowns for clustering: {len(unknowns)}")
                return 0
            
            # Extract embeddings
            embeddings = np.array([u.embedding for u in unknowns if u.embedding])
            
            # Cluster
            engine = AnalyticsEngine(clustering_eps=0.3, clustering_min_samples=3)
            labels, n_clusters, silhouette = engine.cluster_unknowns(embeddings)
            
            # Save cluster patterns
            cluster_count = 0
            for cluster_id in set(labels):
                if cluster_id == -1:  # Skip noise
                    continue
                
                cluster_size = list(labels).count(cluster_id)
                pattern = Pattern(
                    person_id=None,  # Unknown cluster
                    pattern_type="unknown_cluster",
                    confidence=float(silhouette),
                    sighting_count=cluster_size,
                    metadata={"cluster_id": int(cluster_id), "n_clusters": n_clusters},
                    detected_at=datetime.utcnow()
                )
                session.add(pattern)
                cluster_count += 1
            
            await session.commit()
            logger.info(
                f"Clustered {len(unknowns)} unknowns into {n_clusters} clusters "
                f"(silhouette={silhouette:.3f})"
            )
            return cluster_count
    
    return asyncio.run(_run())


# Celery Beat Schedule Configuration
# Add this to api/celery_app.py:
"""
celery_app.conf.beat_schedule = {
    'detect-patterns-daily': {
        'task': 'analytics.detect_patterns',
        'schedule': crontab(hour=2, minute=0),  # 02:00 UTC daily
    },
    'train-anomaly-detector-weekly': {
        'task': 'analytics.train_anomaly_detector',
        'schedule': crontab(hour=3, minute=0, day_of_week=0),  # 03:00 UTC Sunday
    },
    'score-recent-sightings': {
        'task': 'analytics.score_recent_sightings',
        'schedule': timedelta(hours=6),  # Every 6 hours
    },
    'cluster-unknowns-daily': {
        'task': 'analytics.cluster_unknowns',
        'schedule': crontab(hour=4, minute=0),  # 04:00 UTC daily
    },
}
"""
