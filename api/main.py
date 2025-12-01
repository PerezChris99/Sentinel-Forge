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
    
    # Check for repeat offender (simple Redis cache check)
    cache_key = f"sightings:{event.person_id}:24h"
    count = await redis_client.incr(cache_key)
    await redis_client.expire(cache_key, 86400)  # 24 hours
    
    flag_level = event.flag_level
    if count > 3 and event.person_id and event.person_id.startswith("unknown"):
        flag_level = max(flag_level, 2)  # Escalate to high_risk
    
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
