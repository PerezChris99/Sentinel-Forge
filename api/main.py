"""
FastAPI main application for SentinelForge.
Phase 3: Logging & Storage Layer with security, privacy, and ALFIE integration.
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional

import redis.asyncio as redis
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Sighting, Person

# Import extended router and websocket (will configure after app creation)
from api.websocket import attach_socketio

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "changeme-super-secret")
DB_URL = os.getenv("DB_URL", "postgresql+asyncpg://sentinelforge:sentinelforge@localhost:5432/sentinelforge")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ALFIE_WEBHOOK_URL = os.getenv("ALFIE_WEBHOOK_URL", "")
FERNET_KEY = os.getenv("FERNET_KEY", Fernet.generate_key().decode())

# Crypto
fernet = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)

# Database
engine = create_async_engine(DB_URL, echo=False, future=True)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Redis
redis_client: Optional[redis.Redis] = None

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# Pydantic Models
class SightingEvent(BaseModel):
    event_type: str = "sighting"
    timestamp: str
    camera_id: str
    person_id: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    embedding: List[float] = Field(..., min_length=128, max_length=128)
    cropped_b64: str
    flag_level: int = Field(0, ge=0, le=3)
    metadata: dict = {}


class PersonResponse(BaseModel):
    id: str
    name: str
    role: Optional[str]
    known_status: bool
    consent_given: bool
    last_seen: Optional[str]


class ALFIEQuery(BaseModel):
    query_type: str
    person_id: Optional[str] = None
    date_range: Optional[dict] = None


# Lifespan context
@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    yield
    await redis_client.close()


# FastAPI app
app = FastAPI(
    title="SentinelForge API",
    version="0.1.0",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth
security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Simple JWT verification (stub - expand with proper validation)."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# Dependency: DB Session
async def get_db():
    async with async_session_maker() as session:
        yield session


# Include extended API router
from api.extended import router as extended_router
import api.extended as extended_module
extended_module.get_db = get_db  # Inject DB dependency
app.include_router(extended_router, prefix="/api")

# Attach WebSocket
attach_socketio(app)


# Endpoints
@app.get("/")
async def root():
    return {"message": "SentinelForge API v0.1.0"}


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint."""
    try:
        await db.execute("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


@app.post("/log_sighting")
@limiter.limit("100/minute")
async def log_sighting(
    request: Request,
    event: SightingEvent,
    db: AsyncSession = Depends(get_db),
    # auth: dict = Depends(verify_token)  # Uncomment when JWT is configured
):
    """
    Log a sighting event from the detection engine.
    Encrypts embeddings, stores in DB, checks for repeat flags.
    """
    # Encrypt embedding
    embedding_json = str(event.embedding)
    encrypted_embedding = fernet.encrypt(embedding_json.encode()).decode()
    
    # Flag all unknown faces at all hours
    flag_level = event.flag_level
    
    # Unknown faces are always flagged
    if event.person_id and event.person_id.startswith("unknown"):
        flag_level = max(flag_level, 1)  # Flag as suspicious
        
        # Check for repeat offender (simple Redis cache check)
        cache_key = f"sightings:{event.person_id}:24h"
        count = await redis_client.incr(cache_key)
        await redis_client.expire(cache_key, 86400)  # 24 hours
        
        # Escalate repeat unknowns
        if count > 3:
            flag_level = max(flag_level, 2)  # Escalate to high_risk
    else:
        # Known persons: check for repeat sightings
        cache_key = f"sightings:{event.person_id}:24h"
        count = await redis_client.incr(cache_key)
        await redis_client.expire(cache_key, 86400)  # 24 hours
    
    # Create sighting record
    sighting = Sighting(
        person_id=event.person_id if event.person_id and not event.person_id.startswith("unknown") else None,
        timestamp=datetime.fromisoformat(event.timestamp.replace("Z", "+00:00")),
        camera_id=event.camera_id,
        confidence=event.confidence,
        embedding=event.embedding,  # Store as-is (encryption happens at app layer if needed)
        face_image_b64=event.cropped_b64,
        flag_level=flag_level,
        metadata=event.metadata,
    )
    
    db.add(sighting)
    await db.commit()
    await db.refresh(sighting)
    
    # Trigger webhook if flagged
    if flag_level >= 2 and ALFIE_WEBHOOK_URL:
        # TODO: Use Celery task for async webhook
        pass
    
    return {"status": "logged", "sighting_id": str(sighting.id), "flag_level": flag_level}


@app.get("/api/persons", response_model=List[PersonResponse])
async def get_persons(
    status: Optional[str] = "known",
    db: AsyncSession = Depends(get_db),
):
    """Fetch persons list (known or unknown)."""
    from sqlalchemy import select
    
    query = select(Person)
    if status == "known":
        query = query.where(Person.known_status == True)
    
    result = await db.execute(query)
    persons = result.scalars().all()
    
    return [
        PersonResponse(
            id=str(p.id),
            name=p.name,
            role=p.role,
            known_status=p.known_status,
            consent_given=p.consent_given,
            last_seen=None,  # TODO: Query last sighting
        )
        for p in persons
    ]


@app.post("/api/alfie/receive_query")
async def alfie_query(
    query: ALFIEQuery,
    db: AsyncSession = Depends(get_db),
):
    """Inbound endpoint for ALFIE to query patterns or data."""
    # Placeholder implementation
    return {"status": "received", "query_type": query.query_type}


@app.post("/api/alfie/alert")
async def trigger_alfie_alert(payload: dict):
    """
    Outbound webhook trigger (usually called internally via Celery).
    Accepts payload and forwards to ALFIE.
    """
    # TODO: Implement HTTP POST to ALFIE_WEBHOOK_URL
    return {"status": "queued", "payload": payload}


# Dashboard API Endpoints
@app.get("/api/stats/overview")
async def get_overview_stats(db: AsyncSession = Depends(get_db)):
    """Get high-level overview statistics for dashboard header."""
    from sqlalchemy import select, func
    
    # Total persons
    total_persons = await db.scalar(select(func.count(Person.id)))
    
    # Today's sightings
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sightings = await db.scalar(
        select(func.count(Sighting.id)).where(Sighting.timestamp >= today_start)
    )
    
    # Active flags (flag_level >= 1 in last 24h)
    day_ago = datetime.utcnow() - timedelta(days=1)
    active_flags = await db.scalar(
        select(func.count(Sighting.id)).where(
            Sighting.timestamp >= day_ago,
            Sighting.flag_level >= 1
        )
    )
    
    return {
        "total_persons": total_persons or 0,
        "today_sightings": today_sightings or 0,
        "active_flags": active_flags or 0
    }


@app.get("/api/stats/kpis")
async def get_kpi_stats(db: AsyncSession = Depends(get_db)):
    """Get KPI card statistics for overview tab."""
    from sqlalchemy import select, func
    
    # Total sightings
    total_sightings = await db.scalar(select(func.count(Sighting.id)))
    
    # Known persons
    known_persons = await db.scalar(
        select(func.count(Person.id)).where(Person.known_status == True)
    )
    
    # Unknowns in last 90 days
    cutoff_90d = datetime.utcnow() - timedelta(days=90)
    unknowns_90d = await db.scalar(
        select(func.count(Sighting.id)).where(
            Sighting.person_id.is_(None),
            Sighting.timestamp >= cutoff_90d
        )
    )
    
    # Flagged events (all time)
    flagged_events = await db.scalar(
        select(func.count(Sighting.id)).where(Sighting.flag_level >= 1)
    )
    
    return {
        "total_sightings": total_sightings or 0,
        "known_persons": known_persons or 0,
        "unknowns_90d": unknowns_90d or 0,
        "flagged_events": flagged_events or 0
    }


@app.get("/api/sightings/recent")
async def get_recent_sightings(limit: int = 10, db: AsyncSession = Depends(get_db)):
    """Get recent sightings with person information."""
    from sqlalchemy import select
    
    query = (
        select(Sighting)
        .order_by(Sighting.timestamp.desc())
        .limit(limit)
    )
    
    result = await db.execute(query)
    sightings = result.scalars().all()
    
    # Fetch person names
    response = []
    for s in sightings:
        person_name = "Unknown"
        if s.person_id:
            person = await db.get(Person, s.person_id)
            person_name = person.name if person else "Unknown"
        
        response.append({
            "id": str(s.id),
            "person_name": person_name,
            "camera_id": s.camera_id,
            "flag_level": s.flag_level,
            "confidence": s.confidence,
            "timestamp": s.timestamp.isoformat()
        })
    
    return response


@app.get("/api/alerts/recent")
async def get_recent_alerts(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """Get recent flagged events as alerts."""
    from sqlalchemy import select
    
    query = (
        select(Sighting)
        .where(Sighting.flag_level >= 1)
        .order_by(Sighting.timestamp.desc())
        .limit(limit)
    )
    
    result = await db.execute(query)
    sightings = result.scalars().all()
    
    alerts = []
    for s in sightings:
        person_name = "Unknown individual"
        if s.person_id:
            person = await db.get(Person, s.person_id)
            person_name = person.name if person else "Unknown"
        
        level_text = {
            1: "Flagged",
            2: "Repeat offender",
            3: "Critical alert"
        }.get(s.flag_level, "Alert")
        
        message = f"{level_text}: {person_name} detected at {s.camera_id}"
        
        alerts.append({
            "id": str(s.id),
            "timestamp": s.timestamp.isoformat(),
            "message": message,
            "level": s.flag_level
        })
    
    return alerts


@app.get("/api/stats/camera_activity")
async def get_camera_activity(hours: int = 24, db: AsyncSession = Depends(get_db)):
    """Get camera activity data for chart visualization."""
    from sqlalchemy import select, func
    
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    # Simple hourly aggregation
    query = (
        select(
            func.date_trunc('hour', Sighting.timestamp).label('hour'),
            Sighting.camera_id,
            func.count(Sighting.id).label('count')
        )
        .where(Sighting.timestamp >= cutoff)
        .group_by('hour', Sighting.camera_id)
        .order_by('hour')
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    # Format for Chart.js
    cameras = {}
    for row in rows:
        cam_id = row.camera_id
        if cam_id not in cameras:
            cameras[cam_id] = []
        cameras[cam_id].append({
            "hour": row.hour.isoformat(),
            "count": row.count
        })
    
    # Generate labels (last 24 hours)
    labels = []
    for i in range(hours):
        hour = datetime.utcnow() - timedelta(hours=hours-i)
        labels.append(hour.strftime("%H:%M"))
    
    datasets = [
        {
            "camera_id": cam_id,
            "data": [d["count"] for d in data]
        }
        for cam_id, data in cameras.items()
    ]
    
    return {
        "labels": labels,
        "datasets": datasets
    }


@app.get("/api/persons")
async def get_persons_gallery(filter: str = "all", db: AsyncSession = Depends(get_db)):
    """Get persons for gallery view with filtering."""
    from sqlalchemy import select, func
    
    # Base query
    query = select(Person)
    
    if filter == "flagged":
        # Get persons with recent flags
        day_ago = datetime.utcnow() - timedelta(days=7)
        flagged_ids = (
            select(Sighting.person_id)
            .where(
                Sighting.timestamp >= day_ago,
                Sighting.flag_level >= 1,
                Sighting.person_id.isnot(None)
            )
            .distinct()
        )
        query = query.where(Person.id.in_(flagged_ids))
    elif filter == "recent":
        # Get persons with sightings in last 24h
        day_ago = datetime.utcnow() - timedelta(days=1)
        recent_ids = (
            select(Sighting.person_id)
            .where(
                Sighting.timestamp >= day_ago,
                Sighting.person_id.isnot(None)
            )
            .distinct()
        )
        query = query.where(Person.id.in_(recent_ids))
    
    result = await db.execute(query)
    persons = result.scalars().all()
    
    # Get last sighting and count for each person
    response = []
    for p in persons:
        last_sighting_query = (
            select(Sighting)
            .where(Sighting.person_id == p.id)
            .order_by(Sighting.timestamp.desc())
            .limit(1)
        )
        last_sighting = await db.scalar(last_sighting_query)
        
        sighting_count = await db.scalar(
            select(func.count(Sighting.id)).where(Sighting.person_id == p.id)
        )
        
        # Get max flag level
        max_flag = await db.scalar(
            select(func.max(Sighting.flag_level)).where(Sighting.person_id == p.id)
        )
        
        response.append({
            "id": str(p.id),
            "name": p.name,
            "last_sighting": last_sighting.timestamp.isoformat() if last_sighting else None,
            "sighting_count": sighting_count or 0,
            "flag_level": max_flag or 0
        })
    
    return response


@app.get("/api/unknowns")
async def get_unknowns(days: int = 90, db: AsyncSession = Depends(get_db)):
    """Get unknown sightings from past N days."""
    from sqlalchemy import select
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    query = (
        select(Sighting)
        .where(
            Sighting.person_id.is_(None),
            Sighting.timestamp >= cutoff
        )
        .order_by(Sighting.timestamp.desc())
        .limit(100)
    )
    
    result = await db.execute(query)
    sightings = result.scalars().all()
    
    return [
        {
            "id": str(s.id),
            "timestamp": s.timestamp.isoformat(),
            "camera_id": s.camera_id,
            "confidence": s.confidence
        }
        for s in sightings
    ]


@app.get("/api/reports/events")
async def get_event_report(start: str, end: str, db: AsyncSession = Depends(get_db)):
    """Generate event report for date range."""
    from sqlalchemy import select, func
    
    start_date = datetime.fromisoformat(start)
    end_date = datetime.fromisoformat(end) + timedelta(days=1)  # Include end day
    
    # Get events in range
    query = (
        select(Sighting)
        .where(
            Sighting.timestamp >= start_date,
            Sighting.timestamp < end_date
        )
        .order_by(Sighting.timestamp.desc())
    )
    
    result = await db.execute(query)
    sightings = result.scalars().all()
    
    # Calculate summary
    total_events = len(sightings)
    unique_persons = len(set(s.person_id for s in sightings if s.person_id))
    avg_confidence = sum(s.confidence for s in sightings) / total_events if total_events > 0 else 0
    
    events = []
    for s in sightings:
        events.append({
            "id": str(s.id),
            "timestamp": s.timestamp.isoformat(),
            "person_id": str(s.person_id) if s.person_id else None,
            "camera_id": s.camera_id,
            "confidence": s.confidence,
            "flag_level": s.flag_level
        })
    
    return {
        "summary": {
            "total_events": total_events,
            "unique_persons": unique_persons,
            "avg_confidence": avg_confidence
        },
        "events": events[:500]  # Limit to 500 for performance
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
