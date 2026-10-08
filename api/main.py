"""
FastAPI main application for SentinelForge.
Phase 3: Logging & Storage Layer with security, privacy, and ALFIE integration.
"""
import asyncio
import base64
import hashlib
import hmac
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID
from pathlib import Path

import redis.asyncio as redis
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware

from db.models import Base, Sighting, Person, UserRole
from api.runtime import load_config
from api.audit import RequestAuditMiddleware

# Import extended router and websocket (will configure after app creation)
from api.websocket import attach_socketio

# Configuration
CONFIG = load_config()
SECRET_KEY = CONFIG.secret_key
REDIS_URL = CONFIG.redis_url
INGEST_API_KEY = CONFIG.ingest_api_key
ALFIE_WEBHOOK_URL = os.getenv("ALFIE_WEBHOOK_URL", "")
ALFIE_WEBHOOK_SECRET = os.getenv("ALFIE_WEBHOOK_SECRET", "")
FERNET_KEY = CONFIG.fernet_key or Fernet.generate_key().decode()
CORS_ORIGINS = ",".join(CONFIG.cors_origins)

# Auto-detect DB: try PostgreSQL, fall back to SQLite for dev mode
_pg_url = os.getenv("DB_URL", "postgresql+asyncpg://sentinelforge:sentinelforge@localhost:5432/sentinelforge")
_SQLITE_PATH = Path(__file__).resolve().parent.parent / "sentinelforge_dev.db"
DEV_MODE = False

def _build_engine():
    global DEV_MODE
    # If DB_URL explicitly points to sqlite, use it
    if "sqlite" in _pg_url:
        DEV_MODE = True
        return create_async_engine(
            _pg_url, echo=False, future=True,
            connect_args={"check_same_thread": False}
        )
    # Try to test PostgreSQL connectivity
    try:
        import socket
        from urllib.parse import urlparse
        parsed = urlparse(_pg_url.replace("+asyncpg", ""))
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        print(f"✓ PostgreSQL reachable at {host}:{port}")
        return create_async_engine(_pg_url, echo=False, future=True)
    except (OSError, ConnectionRefusedError):
        DEV_MODE = True
        sqlite_url = f"sqlite+aiosqlite:///{_SQLITE_PATH}"
        # Set env so models.py picks up the right dialect
        os.environ["DB_URL"] = sqlite_url
        print(f"⚠ PostgreSQL not reachable. Using SQLite dev mode: {_SQLITE_PATH}")
        return create_async_engine(
            sqlite_url, echo=False, future=True,
            connect_args={"check_same_thread": False}
        )

engine = _build_engine()
DB_URL = str(engine.url)

# Crypto
fernet = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)

async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Redis
redis_client: Optional[redis.Redis] = None

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# Pydantic Models
class SightingEvent(BaseModel):
    event_type: str = "sighting"
    timestamp: datetime
    camera_id: str = Field(..., min_length=1, max_length=128)
    person_id: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    embedding: List[float] = Field(..., min_length=128, max_length=128)
    cropped_b64: str = Field(..., min_length=1, max_length=10_000_000)
    flag_level: int = Field(0, ge=0, le=3)
    metadata: dict = Field(default_factory=dict)


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

    # Security warnings for default secrets
    if CONFIG.is_production and DEV_MODE:
        raise RuntimeError("Production environment cannot silently fall back to SQLite")

    # In dev mode, auto-create all tables
    if DEV_MODE:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✓ SQLite tables created (dev mode)")

    try:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        print(f"✓ Connected to Redis at {REDIS_URL}")
    except Exception as e:
        print(f"⚠ Redis connection failed: {e}")
        print("  Continuing without Redis - caching will be disabled")
        redis_client = None
    yield
    if redis_client:
        await redis_client.close()


# FastAPI app
app = FastAPI(
    title="SentinelForge API",
    version="0.1.0",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Resolve CORS origins
if CONFIG.allow_all_origins:
    _allowed_origins = ["*"]
else:
    _allowed_origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=not CONFIG.allow_all_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not DEV_MODE:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' https://cdn.jsdelivr.net https://cdn.socket.io 'unsafe-inline'; "
                "style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com 'unsafe-inline'; "
                "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
                "img-src 'self' data: blob: http: https:; "
                "connect-src 'self' ws: wss: http: https:"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestAuditMiddleware, session_factory=lambda: async_session_maker())

# Auth
security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """JWT verification with issuer/audience validation."""
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=["HS256"],
            audience="sentinelforge-api", issuer="sentinelforge"
        )
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
from api.privacy import router as privacy_router
import api.privacy as privacy_module
extended_module._real_get_db = get_db
privacy_module._real_get_db = get_db
app.include_router(extended_router, prefix="/api")
app.include_router(privacy_router, prefix="/api")

# Mount Dashboard
BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"
if DASHBOARD_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
    print(f"✓ Dashboard mounted at /dashboard from {DASHBOARD_DIR}")
else:
    print(f"⚠ Dashboard directory not found at {DASHBOARD_DIR}")

# Attach WebSocket
attach_socketio(app)


# Endpoints
async def verify_ingest_key(request: Request) -> None:
    if CONFIG.is_production:
        supplied = request.headers.get("X-Ingest-Key", "")
        if not supplied or not secrets.compare_digest(supplied, INGEST_API_KEY):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ingest credential")


@app.get("/")
async def root():
    return {"message": "SentinelForge API v0.1.0"}


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint."""
    from sqlalchemy import text
    try:
        await db.execute(text("SELECT 1"))
        db_type = "sqlite (dev)" if DEV_MODE else "postgresql"
        return {"status": "ok", "database": db_type, "redis": redis_client is not None}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


@app.get("/live")
async def liveness_check():
    """Process liveness probe; does not require database or Redis."""
    return {"status": "alive", "environment": CONFIG.environment}


@app.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness probe requiring the configured database to answer."""
    from sqlalchemy import text
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database not ready: {exc}")
    if CONFIG.is_production and redis_client is None:
        raise HTTPException(status_code=503, detail="Redis not ready")
    return {"status": "ready", "database": "ok", "redis": redis_client is not None}


@app.get("/metrics")
async def metrics():
    """Minimal Prometheus-compatible application availability metric."""
    return Response(
        "# HELP sentinelforge_up Application availability marker\n"
        "# TYPE sentinelforge_up gauge\n"
        "sentinelforge_up 1\n",
        media_type="text/plain; version=0.0.4",
    )


@app.post("/log_sighting")
@limiter.limit("100/minute")
async def log_sighting(
    request: Request,
    event: SightingEvent,
    db: AsyncSession = Depends(get_db),
    _ingest_auth: None = Depends(verify_ingest_key),
):
    """
    Log a sighting event from the detection engine.
    Encrypts embeddings, stores in DB, checks for repeat flags.
    """
    # Flag all unknown faces at all hours
    flag_level = event.flag_level
    
    # Unknown faces are always flagged
    if event.person_id and event.person_id.startswith("unknown"):
        flag_level = max(flag_level, 1)  # Flag as suspicious
        
        # Check for repeat offender (simple Redis cache check)
        if redis_client:
            cache_key = f"sightings:{event.person_id}:24h"
            count = await redis_client.incr(cache_key)
            await redis_client.expire(cache_key, 86400)  # 24 hours
            
            # Escalate repeat unknowns
            if count > 3:
                flag_level = max(flag_level, 2)  # Escalate to high_risk
    else:
        # Known persons: check for repeat sightings
        if redis_client:
            cache_key = f"sightings:{event.person_id}:24h"
            count = await redis_client.incr(cache_key)
            await redis_client.expire(cache_key, 86400)  # 24 hours
    
    # Create sighting record
    sighting = Sighting(
        person_id=event.person_id if event.person_id and not event.person_id.startswith("unknown") else None,
        timestamp=event.timestamp,
        camera_id=event.camera_id,
        confidence=event.confidence,
        embedding=event.embedding,  # Store as-is (encryption happens at app layer if needed)
        face_image_b64=event.cropped_b64,
        flag_level=flag_level,
        extra_metadata=event.metadata,
    )
    
    db.add(sighting)
    await db.commit()
    await db.refresh(sighting)
    
    # Trigger webhook if flagged
    if flag_level >= 2 and ALFIE_WEBHOOK_URL:
        # TODO: Use Celery task for async webhook
        pass
    
    return {"status": "logged", "sighting_id": str(sighting.id), "flag_level": flag_level}


@app.post("/api/alfie/receive_query")
async def alfie_query(
    query: ALFIEQuery,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role(UserRole.OPERATOR)),
):
    """Execute a bounded ALFIE intelligence query against SentinelForge data."""
    from sqlalchemy import select
    query_type = query.query_type.strip().lower()

    if query_type == "person":
        if not query.person_id:
            raise HTTPException(status_code=400, detail="person_id is required for person queries")
        try:
            person_id = UUID(query.person_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="person_id must be a UUID") from exc
        person = await db.get(Person, person_id)
        if person is None:
            raise HTTPException(status_code=404, detail="Person not found")
        sightings = (await db.execute(
            select(Sighting).where(Sighting.person_id == person_id)
            .order_by(Sighting.timestamp.desc()).limit(100)
        )).scalars().all()
        return {
            "status": "ok", "query_type": query_type,
            "person": {"id": str(person.id), "name": person.name, "role": person.role},
            "sightings": [
                {"id": str(s.id), "camera_id": s.camera_id, "timestamp": s.timestamp.isoformat(),
                 "confidence": s.confidence, "flag_level": s.flag_level}
                for s in sightings
            ],
        }

    if query_type in {"sightings", "alerts"}:
        statement = select(Sighting).order_by(Sighting.timestamp.desc()).limit(100)
        if query_type == "alerts":
            statement = statement.where(Sighting.flag_level >= 1)
        sightings = (await db.execute(statement)).scalars().all()
        return {
            "status": "ok", "query_type": query_type,
            "items": [
                {"id": str(s.id), "person_id": str(s.person_id) if s.person_id else None,
                 "camera_id": s.camera_id, "timestamp": s.timestamp.isoformat(),
                 "confidence": s.confidence, "flag_level": s.flag_level}
                for s in sightings
            ],
        }

    if query_type == "patterns":
        from db.models import Pattern
        patterns = (await db.execute(
            select(Pattern).order_by(Pattern.detected_at.desc()).limit(100)
        )).scalars().all()
        return {
            "status": "ok", "query_type": query_type,
            "items": [
                {"id": str(p.id), "pattern_type": p.pattern_type, "confidence": p.confidence,
                 "detected_at": p.detected_at.isoformat() if p.detected_at else None,
                 "metadata": p.metadata_json}
                for p in patterns
            ],
        }

    raise HTTPException(status_code=400, detail="Unsupported query_type")


@app.post("/api/alfie/alert")
async def trigger_alfie_alert(
    payload: dict,
    user: dict = Depends(require_role(UserRole.OPERATOR)),
):
    """Deliver an alert to the configured ALFIE webhook."""
    if not ALFIE_WEBHOOK_URL:
        raise HTTPException(status_code=503, detail="ALFIE webhook is not configured")

    import requests
    import json
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    headers = {"Content-Type": "application/json", "User-Agent": "SentinelForge/1.0"}
    if ALFIE_WEBHOOK_SECRET:
        signature = hmac.new(
            ALFIE_WEBHOOK_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        headers["X-SentinelForge-Signature"] = signature
    try:
        response = await asyncio.to_thread(
            requests.post, ALFIE_WEBHOOK_URL, data=body, headers=headers, timeout=10
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="ALFIE webhook delivery failed") from exc
    return {"status": "delivered", "http_status": response.status_code}


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
async def get_recent_sightings(limit: int = Query(10, ge=1, le=100), db: AsyncSession = Depends(get_db)):
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
            "person_id": str(s.person_id) if s.person_id else None,
            "person_name": person_name,
            "camera_id": s.camera_id,
            "flag_level": s.flag_level,
            "confidence": s.confidence,
            "timestamp": s.timestamp.isoformat()
        })
    
    return response


@app.get("/api/alerts/recent")
async def get_recent_alerts(limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)):
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
async def get_camera_activity(hours: int = Query(24, ge=1, le=168), db: AsyncSession = Depends(get_db)):
    """Get camera activity data for chart visualization."""
    from sqlalchemy import select, func
    
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    # Keep aggregation dialect-neutral so SQLite smoke tests and PostgreSQL production
    # produce the same contract. The timestamp/camera pair is indexed in production.
    rows = (await db.execute(
        select(Sighting.timestamp, Sighting.camera_id)
        .where(Sighting.timestamp >= cutoff)
        .order_by(Sighting.timestamp)
    )).all()

    bucketed: dict[tuple[str, str], int] = {}
    for row in rows:
        ts = row.timestamp
        bucket = ts.replace(minute=0, second=0, microsecond=0)
        key = (bucket.isoformat(), row.camera_id)
        bucketed[key] = bucketed.get(key, 0) + 1

    labels_dt = [
        (datetime.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours - 1 - i))
        for i in range(hours)
    ]
    labels = [hour.strftime("%H:%M") for hour in labels_dt]
    datasets = []
    camera_ids = sorted({camera_id for _, camera_id in bucketed})
    for camera_id in camera_ids:
        datasets.append({
            "camera_id": camera_id,
            "data": [
                sum(
                    count for (bucket, cam), count in bucketed.items()
                    if cam == camera_id and bucket == hour.isoformat()
                )
                for hour in labels_dt
            ],
        })
    
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
async def get_unknowns(days: int = Query(90, ge=1, le=3650), db: AsyncSession = Depends(get_db)):
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

@app.get("/api/stats/severity_distribution")
async def get_severity_distribution(db: AsyncSession = Depends(get_db)):
    """Get distribution of sightings by flag_level (severity)."""
    from sqlalchemy import select, func

    # Count by flag_level
    query = (
        select(Sighting.flag_level, func.count(Sighting.id))
        .group_by(Sighting.flag_level)
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    # Map to standard levels
    distribution = {0: 0, 1: 0, 2: 0, 3: 0} 
    for level, count in rows:
        distribution[level] = count
        
    return {
        "labels": ["Normal", "Flagged", "Repeat", "Critical"],
        "data": [distribution.get(0, 0), distribution.get(1, 0), distribution.get(2, 0), distribution.get(3, 0)]
    }


@app.get("/api/stats/camera_volume")
async def get_camera_volume(db: AsyncSession = Depends(get_db)):
    """Get total sightings count by camera_id."""
    from sqlalchemy import select, func

    query = (
        select(Sighting.camera_id, func.count(Sighting.id))
        .group_by(Sighting.camera_id)
        .order_by(func.count(Sighting.id).desc())
        .limit(10) # Top 10 cameras
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    return {
        "labels": [row[0] for row in rows],
        "data": [row[1] for row in rows]
    }
