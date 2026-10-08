"""
Extended API endpoints for authentication, camera management, alerts, incidents, and search
"""
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID
import base64

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Request
from pydantic import BaseModel, Field, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

try:
    import face_recognition
    import numpy as np
    _HAS_FACE_RECOGNITION = True
except ImportError:
    _HAS_FACE_RECOGNITION = False

from db.models import (
    User, UserRole, Camera, CameraStatus, CameraType, Alert, AlertStatus,
    Incident, IncidentStatus, IncidentEvent, Person, Sighting,
    AuditLog, SearchQuery, DetectedObject, Track,
    BehaviorEventRecord, Vehicle, ZoneRecord, EntityRelationship
)
from api.auth import (
    get_current_user, require_role, get_password_hash,
    verify_password, create_access_token
)


# DB Dependency — resolved at call time from the module attribute
# main.py sets: extended_module.get_db = <real get_db>
_real_get_db = None

async def get_db():
    """Delegates to the real get_db injected by main.py"""
    if _real_get_db is not None:
        async for session in _real_get_db():
            yield session
    else:
        raise RuntimeError("Database dependency not configured")


# Router
router = APIRouter()

# Rate limiter for auth endpoints (brute-force protection)
limiter = Limiter(key_func=get_remote_address)


# ===== AUTHENTICATION ENDPOINTS =====

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    role: UserRole = UserRole.VIEWER


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/auth/register", response_model=TokenResponse, tags=["Authentication"])
@limiter.limit("5/minute")
async def register(request: Request, user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user"""
    # Check if username/email exists
    result = await db.execute(
        select(User).where(
            or_(User.username == user_data.username, User.email == user_data.email)
        )
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists"
        )
    
    # Create user
    user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
        is_active=True,
        created_at=datetime.utcnow()
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Create token
    access_token = create_access_token(data={"sub": str(user.id), "username": user.username, "role": user.role.value})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role.value
        }
    }


@router.post("/auth/login", response_model=TokenResponse, tags=["Authentication"])
@limiter.limit("10/minute")
async def login(request: Request, credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login user and return JWT token"""
    result = await db.execute(
        select(User).where(User.username == credentials.username)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()
    
    # Create token
    access_token = create_access_token(data={"sub": str(user.id), "username": user.username, "role": user.role.value})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "full_name": user.full_name
        }
    }


@router.get("/auth/me", tags=["Authentication"])
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user info"""
    return {
        "id": user["id"],
        "username": user.get("username", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "viewer"),
        "full_name": user.get("full_name", "")
    }


# ===== CAMERA MANAGEMENT ENDPOINTS =====

class CameraCreate(BaseModel):
    name: str
    camera_id: str
    stream_url: str  # IP Webcam URL / RTSP / device index
    camera_type: Optional[str] = None  # ip_webcam, rtsp, usb, file, http — auto-detected if omitted
    location: Optional[str] = None
    zone: Optional[str] = None
    extra_metadata: Optional[dict] = {}


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    stream_url: Optional[str] = None
    camera_type: Optional[str] = None
    location: Optional[str] = None
    zone: Optional[str] = None
    is_enabled: Optional[bool] = None
    extra_metadata: Optional[dict] = None


@router.post("/cameras", tags=["Cameras"])
async def create_camera(
    camera_data: CameraCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Create a new camera"""
    # Check if camera_id already exists
    result = await db.execute(select(Camera).where(Camera.camera_id == camera_data.camera_id))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Camera ID already exists"
        )
    
    from detection.sources import detect_camera_type, validate_stream_url, CameraType as SourceCameraType

    # Validate stream URL
    is_valid, reason = validate_stream_url(camera_data.stream_url)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid stream URL: {reason}")

    # Auto-detect camera type if not provided
    cam_type_str = camera_data.camera_type
    if not cam_type_str:
        cam_type_str = detect_camera_type(camera_data.stream_url).value

    # Derive snapshot URL for IP Webcam Pro
    snapshot_url = None
    if cam_type_str == "ip_webcam":
        from urllib.parse import urlparse
        parsed = urlparse(camera_data.stream_url)
        snapshot_url = f"{parsed.scheme}://{parsed.netloc}/shot.jpg"

    camera = Camera(
        name=camera_data.name,
        camera_id=camera_data.camera_id,
        camera_type=CameraType(cam_type_str),
        stream_url=camera_data.stream_url,
        snapshot_url=snapshot_url,
        location=camera_data.location,
        zone=camera_data.zone,
        status=CameraStatus.OFFLINE,
        is_enabled=True,
        created_at=datetime.utcnow(),
        extra_metadata=camera_data.extra_metadata
    )
    
    db.add(camera)
    await db.commit()
    await db.refresh(camera)
    
    return {
        "id": str(camera.id),
        "name": camera.name,
        "camera_id": camera.camera_id,
        "camera_type": camera.camera_type.value,
        "stream_url": camera.stream_url,
        "location": camera.location,
        "zone": camera.zone,
        "status": camera.status.value,
        "is_enabled": camera.is_enabled
    }


@router.get("/cameras", tags=["Cameras"])
async def list_cameras(
    db: AsyncSession = Depends(get_db),
    enabled_only: bool = False
):
    """List all cameras"""
    query = select(Camera)
    if enabled_only:
        query = query.where(Camera.is_enabled == True)
    
    result = await db.execute(query)
    cameras = result.scalars().all()
    
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "camera_id": c.camera_id,
            "camera_type": c.camera_type.value if c.camera_type else "ip_webcam",
            "stream_url": c.stream_url,
            "location": c.location,
            "zone": c.zone,
            "status": c.status.value,
            "is_enabled": c.is_enabled,
            "last_seen": c.last_seen.isoformat() if c.last_seen else None
        }
        for c in cameras
    ]


@router.get("/cameras/{camera_id}", tags=["Cameras"])
async def get_camera(camera_id: str, db: AsyncSession = Depends(get_db)):
    """Get camera details"""
    result = await db.execute(select(Camera).where(Camera.camera_id == camera_id))
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    return {
        "id": str(camera.id),
        "name": camera.name,
        "camera_id": camera.camera_id,
        "camera_type": camera.camera_type.value if camera.camera_type else "ip_webcam",
        "stream_url": camera.stream_url,
        "snapshot_url": camera.snapshot_url,
        "location": camera.location,
        "zone": camera.zone,
        "status": camera.status.value,
        "is_enabled": camera.is_enabled,
        "created_at": camera.created_at.isoformat(),
        "last_seen": camera.last_seen.isoformat() if camera.last_seen else None,
        "extra_metadata": camera.extra_metadata
    }


@router.put("/cameras/{camera_id}", tags=["Cameras"])
async def update_camera(
    camera_id: str,
    camera_data: CameraUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Update camera settings"""
    result = await db.execute(select(Camera).where(Camera.camera_id == camera_id))
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Update fields
    if camera_data.name is not None:
        camera.name = camera_data.name
    if camera_data.stream_url is not None:
        from detection.sources import validate_stream_url
        is_valid, reason = validate_stream_url(camera_data.stream_url)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid stream URL: {reason}")
        camera.stream_url = camera_data.stream_url
    if camera_data.camera_type is not None:
        camera.camera_type = CameraType(camera_data.camera_type)
    if camera_data.location is not None:
        camera.location = camera_data.location
    if camera_data.zone is not None:
        camera.zone = camera_data.zone
    if camera_data.is_enabled is not None:
        camera.is_enabled = camera_data.is_enabled
    if camera_data.extra_metadata is not None:
        camera.extra_metadata = camera_data.extra_metadata
    
    await db.commit()
    
    return {"status": "updated", "camera_id": camera_id}


@router.delete("/cameras/{camera_id}", tags=["Cameras"])
async def delete_camera(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN))
):
    """Delete a camera"""
    result = await db.execute(select(Camera).where(Camera.camera_id == camera_id))
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    await db.delete(camera)
    await db.commit()
    
    return {"status": "deleted", "camera_id": camera_id}


@router.post("/cameras/{camera_id}/heartbeat", tags=["Cameras"])
async def camera_heartbeat(camera_id: str, db: AsyncSession = Depends(get_db)):
    """Update camera last seen (heartbeat)"""
    result = await db.execute(select(Camera).where(Camera.camera_id == camera_id))
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    camera.last_seen = datetime.utcnow()
    camera.status = CameraStatus.ONLINE
    await db.commit()
    
    return {"status": "ok", "last_seen": camera.last_seen.isoformat()}


@router.post("/cameras/{camera_id}/test", tags=["Cameras"])
async def test_camera_connection(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Test camera stream connectivity and return health status."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    result = await db.execute(select(Camera).where(Camera.camera_id == camera_id))
    camera = result.scalar_one_or_none()

    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    from detection.sources import create_source
    source = create_source(
        camera.stream_url,
        camera.camera_id,
        camera.camera_type.value if camera.camera_type else None,
    )

    # Run blocking health_check in thread pool with timeout
    loop = asyncio.get_event_loop()
    try:
        health = await asyncio.wait_for(
            loop.run_in_executor(None, source.health_check),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        health = {"status": "error", "detail": "Connection timed out (10s)", "latency_ms": 10000}
    finally:
        source.release()

    # Update camera status based on health check
    if health["status"] == "online":
        camera.status = CameraStatus.ONLINE
        camera.last_seen = datetime.utcnow()
    else:
        camera.status = CameraStatus.ERROR
    await db.commit()

    return {
        "camera_id": camera_id,
        "camera_type": camera.camera_type.value if camera.camera_type else "unknown",
        **health,
    }


@router.get("/cameras/{camera_id}/snapshot", tags=["Cameras"])
async def get_camera_snapshot(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Grab a single JPEG snapshot from the camera."""
    result = await db.execute(select(Camera).where(Camera.camera_id == camera_id))
    camera = result.scalar_one_or_none()

    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    from detection.sources import create_source
    import cv2
    source = create_source(
        camera.stream_url,
        camera.camera_id,
        camera.camera_type.value if camera.camera_type else None,
    )
    frame = source.get_snapshot()
    source.release()

    if frame is None:
        raise HTTPException(status_code=503, detail="Failed to capture snapshot")

    _, buffer = cv2.imencode(".jpg", frame)
    from fastapi.responses import Response
    return Response(content=buffer.tobytes(), media_type="image/jpeg")


# ===== PERSON MANAGEMENT ENDPOINTS =====

class PersonCreate(BaseModel):
    name: str
    role: Optional[str] = None
    notes: Optional[str] = None
    consent_given: bool = False


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    notes: Optional[str] = None
    consent_given: Optional[bool] = None
    is_archived: Optional[bool] = None


@router.post("/persons", tags=["Persons"])
async def create_person(
    person_data: PersonCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Create a new person"""
    person = Person(
        name=person_data.name,
        role=person_data.role,
        notes=person_data.notes,
        consent_given=person_data.consent_given,
        photo_urls=[],
        is_archived=False,
        created_at=datetime.utcnow()
    )
    
    db.add(person)
    await db.commit()
    await db.refresh(person)
    
    return {
        "id": str(person.id),
        "name": person.name,
        "role": person.role,
        "notes": person.notes,
        "consent_given": person.consent_given
    }


@router.get("/persons", tags=["Persons"])
async def list_persons(
    db: AsyncSession = Depends(get_db),
    include_archived: bool = False,
    search: Optional[str] = None
):
    """List all persons"""
    query = select(Person)
    
    if not include_archived:
        query = query.where(Person.is_archived == False)
    
    if search:
        query = query.where(
            or_(
                Person.name.ilike(f"%{search}%"),
                Person.role.ilike(f"%{search}%")
            )
        )
    
    result = await db.execute(query)
    persons = result.scalars().all()
    
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "role": p.role,
            "notes": p.notes,
            "consent_given": p.consent_given,
            "photo_count": len(p.photo_urls) if p.photo_urls else 0,
            "is_archived": p.is_archived,
            "created_at": p.created_at.isoformat()
        }
        for p in persons
    ]


@router.get("/persons/{person_id}", tags=["Persons"])
async def get_person(person_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get person details"""
    result = await db.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # Get sighting count
    sighting_count_result = await db.execute(
        select(func.count(Sighting.id)).where(Sighting.person_id == person_id)
    )
    sighting_count = sighting_count_result.scalar()
    
    return {
        "id": str(person.id),
        "name": person.name,
        "role": person.role,
        "notes": person.notes,
        "consent_given": person.consent_given,
        "photo_urls": person.photo_urls,
        "is_archived": person.is_archived,
        "created_at": person.created_at.isoformat(),
        "sighting_count": sighting_count
    }


@router.put("/persons/{person_id}", tags=["Persons"])
async def update_person(
    person_id: UUID,
    person_data: PersonUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Update person information"""
    result = await db.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    if person_data.name is not None:
        person.name = person_data.name
    if person_data.role is not None:
        person.role = person_data.role
    if person_data.notes is not None:
        person.notes = person_data.notes
    if person_data.consent_given is not None:
        person.consent_given = person_data.consent_given
    if person_data.is_archived is not None:
        person.is_archived = person_data.is_archived
    
    await db.commit()
    
    return {"status": "updated", "person_id": str(person_id)}


@router.post("/persons/{person_id}/photos", tags=["Persons"])
async def upload_person_photo(
    person_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Upload a photo for a person and extract face embedding"""
    if not _HAS_FACE_RECOGNITION:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="face_recognition library not installed"
        )
    import numpy as np
    result = await db.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # Read image
    contents = await file.read()
    
    # Convert to numpy array
    nparr = np.frombuffer(contents, np.uint8)
    import cv2
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Extract face embedding
    face_locations = face_recognition.face_locations(rgb)
    
    if not face_locations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No face detected in image"
        )
    
    face_encodings = face_recognition.face_encodings(rgb, face_locations)
    
    if not face_encodings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract face encoding"
        )
    
    # Store photo as base64
    photo_base64 = base64.b64encode(contents).decode('utf-8')
    photo_url = f"data:image/jpeg;base64,{photo_base64}"
    
    # Update person
    if not person.photo_urls:
        person.photo_urls = []
    person.photo_urls.append(photo_url)
    
    # Update or create face embedding
    if person.face_embedding is None:
        person.face_embedding = face_encodings[0].tolist()
    
    await db.commit()
    
    return {
        "status": "uploaded",
        "person_id": str(person_id),
        "photo_count": len(person.photo_urls)
    }


@router.delete("/persons/{person_id}", tags=["Persons"])
async def delete_person(
    person_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN))
):
    """Delete a person (soft delete via archive)"""
    result = await db.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    person.is_archived = True
    await db.commit()
    
    return {"status": "archived", "person_id": str(person_id)}


# ===== ALERT MANAGEMENT ENDPOINTS =====

class AlertUpdate(BaseModel):
    status: Optional[AlertStatus] = None
    assigned_to: Optional[UUID] = None


@router.get("/alerts", tags=["Alerts"])
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    status: Optional[AlertStatus] = None,
    severity: Optional[int] = None,
    limit: int = 100
):
    """List alerts with optional filtering"""
    query = select(Alert).order_by(Alert.created_at.desc())
    
    if status:
        query = query.where(Alert.status == status)
    if severity:
        query = query.where(Alert.severity == severity)
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    alerts = result.scalars().all()
    
    return [
        {
            "id": str(a.id),
            "sighting_id": str(a.sighting_id),
            "alert_type": a.alert_type,
            "severity": a.severity,
            "status": a.status.value,
            "message": a.message,
            "assigned_to": str(a.assigned_to) if a.assigned_to else None,
            "created_at": a.created_at.isoformat(),
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None
        }
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/acknowledge", tags=["Alerts"])
async def acknowledge_alert(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Acknowledge an alert"""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_at = datetime.utcnow()
    alert.assigned_to = user.id
    
    await db.commit()
    
    return {"status": "acknowledged", "alert_id": str(alert_id)}


@router.post("/alerts/{alert_id}/dismiss", tags=["Alerts"])
async def dismiss_alert(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Dismiss an alert"""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.status = AlertStatus.DISMISSED
    alert.resolved_at = datetime.utcnow()
    
    await db.commit()
    
    return {"status": "dismissed", "alert_id": str(alert_id)}


@router.post("/alerts/{alert_id}/escalate", tags=["Alerts"])
async def escalate_alert(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Escalate an alert"""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.status = AlertStatus.ESCALATED
    alert.severity = min(alert.severity + 1, 4)  # Max severity is 4
    
    await db.commit()
    
    return {"status": "escalated", "alert_id": str(alert_id), "new_severity": alert.severity}


# ===== INCIDENT MANAGEMENT ENDPOINTS =====

class IncidentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    person_id: Optional[UUID] = None
    camera_id: Optional[str] = None
    severity: int = Field(1, ge=1, le=4)


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[IncidentStatus] = None
    severity: Optional[int] = Field(None, ge=1, le=4)
    assigned_to: Optional[UUID] = None


@router.post("/incidents", tags=["Incidents"])
async def create_incident(
    incident_data: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Create a new incident"""
    incident = Incident(
        title=incident_data.title,
        description=incident_data.description,
        person_id=incident_data.person_id,
        camera_id=incident_data.camera_id,
        severity=incident_data.severity,
        status=IncidentStatus.OPEN,
        created_by=user.id,
        created_at=datetime.utcnow()
    )
    
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    
    return {
        "id": str(incident.id),
        "title": incident.title,
        "status": incident.status.value,
        "severity": incident.severity
    }


@router.get("/incidents", tags=["Incidents"])
async def list_incidents(
    db: AsyncSession = Depends(get_db),
    status: Optional[IncidentStatus] = None,
    limit: int = 50
):
    """List incidents"""
    query = select(Incident).order_by(Incident.created_at.desc())
    
    if status:
        query = query.where(Incident.status == status)
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    incidents = result.scalars().all()
    
    return [
        {
            "id": str(i.id),
            "title": i.title,
            "description": i.description,
            "status": i.status.value,
            "severity": i.severity,
            "person_id": str(i.person_id) if i.person_id else None,
            "camera_id": i.camera_id,
            "created_at": i.created_at.isoformat(),
            "assigned_to": str(i.assigned_to) if i.assigned_to else None
        }
        for i in incidents
    ]


@router.get("/incidents/{incident_id}", tags=["Incidents"])
async def get_incident(incident_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get incident details with events"""
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    # Get events
    events_result = await db.execute(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.created_at.asc())
    )
    events = events_result.scalars().all()
    
    return {
        "id": str(incident.id),
        "title": incident.title,
        "description": incident.description,
        "status": incident.status.value,
        "severity": incident.severity,
        "person_id": str(incident.person_id) if incident.person_id else None,
        "camera_id": incident.camera_id,
        "created_at": incident.created_at.isoformat(),
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "created_by": str(incident.created_by),
        "assigned_to": str(incident.assigned_to) if incident.assigned_to else None,
        "events": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "description": e.description,
                "sighting_id": str(e.sighting_id) if e.sighting_id else None,
                "created_at": e.created_at.isoformat(),
                "created_by": str(e.created_by)
            }
            for e in events
        ]
    }


@router.put("/incidents/{incident_id}", tags=["Incidents"])
async def update_incident(
    incident_id: UUID,
    incident_data: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Update incident"""
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    if incident_data.title is not None:
        incident.title = incident_data.title
    if incident_data.description is not None:
        incident.description = incident_data.description
    if incident_data.status is not None:
        old_status = incident.status
        incident.status = incident_data.status
        
        # Auto-set resolved_at
        if incident_data.status == IncidentStatus.RESOLVED:
            incident.resolved_at = datetime.utcnow()
        
        # Create event for status change
        event = IncidentEvent(
            incident_id=incident_id,
            event_type="status_change",
            description=f"Status changed from {old_status.value} to {incident_data.status.value}",
            created_by=user.id,
            created_at=datetime.utcnow()
        )
        db.add(event)
    
    if incident_data.severity is not None:
        incident.severity = incident_data.severity
    if incident_data.assigned_to is not None:
        incident.assigned_to = incident_data.assigned_to
    
    await db.commit()
    
    return {"status": "updated", "incident_id": str(incident_id)}


@router.post("/incidents/{incident_id}/events", tags=["Incidents"])
async def add_incident_event(
    incident_id: UUID,
    event_type: str,
    description: str,
    sighting_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Add an event to an incident"""
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Incident not found")
    
    event = IncidentEvent(
        incident_id=incident_id,
        event_type=event_type,
        description=description,
        sighting_id=sighting_id,
        created_by=user.id,
        created_at=datetime.utcnow()
    )
    
    db.add(event)
    await db.commit()
    
    return {"status": "created", "event_id": str(event.id)}


# ===== SEARCH ENDPOINTS =====

@router.get("/search", tags=["Search"])
async def search_all(
    query: str,
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    user: User = Depends(get_current_user)
):
    """Full-text search across persons, sightings, and incidents"""
    # Search persons
    persons_result = await db.execute(
        select(Person)
        .where(
            or_(
                Person.name.ilike(f"%{query}%"),
                Person.role.ilike(f"%{query}%"),
                Person.notes.ilike(f"%{query}%")
            )
        )
        .limit(limit)
    )
    persons = persons_result.scalars().all()
    
    # Search incidents
    incidents_result = await db.execute(
        select(Incident)
        .where(
            or_(
                Incident.title.ilike(f"%{query}%"),
                Incident.description.ilike(f"%{query}%")
            )
        )
        .limit(limit)
    )
    incidents = incidents_result.scalars().all()
    
    # Log search
    search_log = SearchQuery(
        user_id=user.id,
        query_text=query,
        result_count=len(persons) + len(incidents),
        created_at=datetime.utcnow()
    )
    db.add(search_log)
    await db.commit()
    
    return {
        "query": query,
        "persons": [
            {
                "id": str(p.id),
                "name": p.name,
                "role": p.role,
                "type": "person"
            }
            for p in persons
        ],
        "incidents": [
            {
                "id": str(i.id),
                "title": i.title,
                "status": i.status.value,
                "type": "incident"
            }
            for i in incidents
        ]
    }


# ===== EXPORT ENDPOINTS =====

@router.get("/export/csv", tags=["Export"])
async def export_csv(
    db: AsyncSession = Depends(get_db),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Export sightings data as CSV"""
    import csv
    from io import StringIO
    
    query = select(Sighting)
    
    if start_date:
        query = query.where(Sighting.timestamp >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.where(Sighting.timestamp <= datetime.fromisoformat(end_date))
    
    result = await db.execute(query.limit(10000))
    sightings = result.scalars().all()
    
    # Create CSV
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'timestamp', 'person_id', 'camera_id', 'confidence', 'flag_level'
    ])
    writer.writeheader()
    
    for s in sightings:
        writer.writerow({
            'timestamp': s.timestamp.isoformat(),
            'person_id': s.person_id,
            'camera_id': s.camera_id,
            'confidence': s.confidence,
            'flag_level': s.flag_level
        })
    
    from fastapi.responses import Response
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sightings_export.csv"}
    )


# ===== DETECTION & TRACKING ENDPOINTS =====

class DetectedObjectCreate(BaseModel):
    track_id: Optional[str] = None
    object_class: str
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    bbox: List[int] = Field(..., min_length=4, max_length=4)
    camera_id: str
    extra_metadata: Optional[dict] = None


class TrackCreate(BaseModel):
    track_label: str
    camera_id: str
    object_class: Optional[str] = None
    extra_metadata: Optional[dict] = None


@router.post("/detections", tags=["Detections"])
async def create_detection(
    data: DetectedObjectCreate,
    db: AsyncSession = Depends(get_db)
):
    """Log a detected object from the detection pipeline."""
    obj = DetectedObject(
        track_id=data.track_id,
        object_class=data.object_class,
        confidence=data.confidence,
        bbox=data.bbox,
        camera_id=data.camera_id,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        extra_metadata=data.extra_metadata,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {
        "id": str(obj.id),
        "track_id": obj.track_id,
        "object_class": obj.object_class,
        "camera_id": obj.camera_id,
    }


@router.get("/detections", tags=["Detections"])
async def list_detections(
    db: AsyncSession = Depends(get_db),
    camera_id: Optional[str] = None,
    object_class: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List recent detected objects with optional filters."""
    query = select(DetectedObject).order_by(DetectedObject.last_seen.desc())
    if camera_id:
        query = query.where(DetectedObject.camera_id == camera_id)
    if object_class:
        query = query.where(DetectedObject.object_class == object_class)
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    objects = result.scalars().all()
    return [
        {
            "id": str(o.id),
            "track_id": o.track_id,
            "object_class": o.object_class,
            "confidence": o.confidence,
            "bbox": o.bbox,
            "camera_id": o.camera_id,
            "first_seen": o.first_seen.isoformat() if o.first_seen else None,
            "last_seen": o.last_seen.isoformat() if o.last_seen else None,
        }
        for o in objects
    ]


@router.get("/detections/{detection_id}", tags=["Detections"])
async def get_detection(detection_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a single detection by ID."""
    result = await db.execute(select(DetectedObject).where(DetectedObject.id == detection_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Detection not found")
    return {
        "id": str(obj.id),
        "track_id": obj.track_id,
        "object_class": obj.object_class,
        "confidence": obj.confidence,
        "bbox": obj.bbox,
        "camera_id": obj.camera_id,
        "first_seen": obj.first_seen.isoformat() if obj.first_seen else None,
        "last_seen": obj.last_seen.isoformat() if obj.last_seen else None,
        "extra_metadata": obj.extra_metadata,
    }


# ===== TRACKS =====

@router.post("/tracks", tags=["Tracks"])
async def create_track(
    data: TrackCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create or register a new track."""
    # Check uniqueness
    existing = await db.execute(select(Track).where(Track.track_label == data.track_label))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Track label already exists")

    track = Track(
        track_label=data.track_label,
        camera_id=data.camera_id,
        object_class=data.object_class,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        is_active=True,
        extra_metadata=data.extra_metadata,
    )
    db.add(track)
    await db.commit()
    await db.refresh(track)
    return {
        "id": str(track.id),
        "track_label": track.track_label,
        "camera_id": track.camera_id,
        "object_class": track.object_class,
    }


@router.get("/tracks", tags=["Tracks"])
async def list_tracks(
    db: AsyncSession = Depends(get_db),
    camera_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List tracks with optional filters."""
    query = select(Track).order_by(Track.last_seen.desc())
    if camera_id:
        query = query.where(Track.camera_id == camera_id)
    if is_active is not None:
        query = query.where(Track.is_active == is_active)
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    tracks = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "track_label": t.track_label,
            "camera_id": t.camera_id,
            "object_class": t.object_class,
            "is_active": t.is_active,
            "first_seen": t.first_seen.isoformat() if t.first_seen else None,
            "last_seen": t.last_seen.isoformat() if t.last_seen else None,
        }
        for t in tracks
    ]


@router.get("/tracks/{track_label}", tags=["Tracks"])
async def get_track(track_label: str, db: AsyncSession = Depends(get_db)):
    """Get a track by its label."""
    result = await db.execute(select(Track).where(Track.track_label == track_label))
    track = result.scalar_one_or_none()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return {
        "id": str(track.id),
        "track_label": track.track_label,
        "camera_id": track.camera_id,
        "object_class": track.object_class,
        "is_active": track.is_active,
        "first_seen": track.first_seen.isoformat() if track.first_seen else None,
        "last_seen": track.last_seen.isoformat() if track.last_seen else None,
        "extra_metadata": track.extra_metadata,
    }


@router.put("/tracks/{track_label}/deactivate", tags=["Tracks"])
async def deactivate_track(
    track_label: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.OPERATOR)),
):
    """Mark a track as inactive (ended)."""
    result = await db.execute(select(Track).where(Track.track_label == track_label))
    track = result.scalar_one_or_none()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    track.is_active = False
    track.last_seen = datetime.utcnow()
    await db.commit()
    return {"status": "deactivated", "track_label": track_label}


# ===== BEHAVIOR EVENTS =====

class BehaviorEventCreate(BaseModel):
    behavior_type: str
    severity: int = Field(1, ge=1, le=4)
    track_id: Optional[str] = None
    camera_id: Optional[str] = None
    zone_id: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[dict] = None


@router.post("/behaviors", tags=["Behaviors"])
async def create_behavior_event(
    data: BehaviorEventCreate,
    db: AsyncSession = Depends(get_db)
):
    """Log a behavior analysis event."""
    record = BehaviorEventRecord(
        behavior_type=data.behavior_type,
        severity=data.severity,
        track_id=data.track_id,
        camera_id=data.camera_id,
        zone_id=data.zone_id,
        timestamp=datetime.utcnow(),
        description=data.description,
        extra_metadata=data.metadata,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {
        "id": str(record.id),
        "behavior_type": record.behavior_type,
        "severity": record.severity,
        "track_id": record.track_id,
    }


@router.get("/behaviors", tags=["Behaviors"])
async def list_behavior_events(
    db: AsyncSession = Depends(get_db),
    behavior_type: Optional[str] = None,
    zone_id: Optional[str] = None,
    camera_id: Optional[str] = None,
    min_severity: int = 1,
    limit: int = 100,
    offset: int = 0,
):
    """List behavior events with optional filters."""
    query = select(BehaviorEventRecord).order_by(BehaviorEventRecord.timestamp.desc())
    if behavior_type:
        query = query.where(BehaviorEventRecord.behavior_type == behavior_type)
    if zone_id:
        query = query.where(BehaviorEventRecord.zone_id == zone_id)
    if camera_id:
        query = query.where(BehaviorEventRecord.camera_id == camera_id)
    if min_severity > 1:
        query = query.where(BehaviorEventRecord.severity >= min_severity)
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "behavior_type": r.behavior_type,
            "severity": r.severity,
            "track_id": r.track_id,
            "camera_id": r.camera_id,
            "zone_id": r.zone_id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "description": r.description,
        }
        for r in records
    ]


@router.get("/behaviors/stats", tags=["Behaviors"])
async def behavior_stats(
    db: AsyncSession = Depends(get_db),
    hours: int = 24,
):
    """Return aggregated behavior event counts by type."""
    since = datetime.utcnow() - timedelta(hours=hours)
    query = (
        select(
            BehaviorEventRecord.behavior_type,
            func.count(BehaviorEventRecord.id).label("count"),
            func.avg(BehaviorEventRecord.severity).label("avg_severity"),
        )
        .where(BehaviorEventRecord.timestamp >= since)
        .group_by(BehaviorEventRecord.behavior_type)
    )
    result = await db.execute(query)
    rows = result.all()
    return [
        {"behavior_type": r[0], "count": r[1], "avg_severity": round(float(r[2]), 2)}
        for r in rows
    ]


# ===== VEHICLES =====

class VehicleCreate(BaseModel):
    track_id: Optional[str] = None
    vehicle_type: str
    color: Optional[str] = None
    plate_text: Optional[str] = None
    plate_confidence: Optional[float] = None
    camera_id: Optional[str] = None
    extra_metadata: Optional[dict] = None


@router.post("/vehicles", tags=["Vehicles"])
async def create_vehicle(
    data: VehicleCreate,
    db: AsyncSession = Depends(get_db)
):
    """Log a vehicle detection / LPR result."""
    vehicle = Vehicle(
        track_id=data.track_id,
        vehicle_type=data.vehicle_type,
        color=data.color,
        plate_text=data.plate_text,
        plate_confidence=data.plate_confidence,
        camera_id=data.camera_id,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        extra_metadata=data.extra_metadata,
    )
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    return {
        "id": str(vehicle.id),
        "vehicle_type": vehicle.vehicle_type,
        "plate_text": vehicle.plate_text,
        "camera_id": vehicle.camera_id,
    }


@router.get("/vehicles", tags=["Vehicles"])
async def list_vehicles(
    db: AsyncSession = Depends(get_db),
    plate_text: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    color: Optional[str] = None,
    camera_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List vehicles with optional filters."""
    query = select(Vehicle).order_by(Vehicle.last_seen.desc())
    if plate_text:
        query = query.where(Vehicle.plate_text.ilike(f"%{plate_text}%"))
    if vehicle_type:
        query = query.where(Vehicle.vehicle_type == vehicle_type)
    if color:
        query = query.where(Vehicle.color == color)
    if camera_id:
        query = query.where(Vehicle.camera_id == camera_id)
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    vehicles = result.scalars().all()
    return [
        {
            "id": str(v.id),
            "track_id": v.track_id,
            "vehicle_type": v.vehicle_type,
            "color": v.color,
            "plate_text": v.plate_text,
            "plate_confidence": v.plate_confidence,
            "camera_id": v.camera_id,
            "first_seen": v.first_seen.isoformat() if v.first_seen else None,
            "last_seen": v.last_seen.isoformat() if v.last_seen else None,
        }
        for v in vehicles
    ]


@router.get("/vehicles/search/{plate}", tags=["Vehicles"])
async def search_vehicle_by_plate(
    plate: str,
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    """Search vehicles by partial plate number."""
    query = (
        select(Vehicle)
        .where(Vehicle.plate_text.ilike(f"%{plate}%"))
        .order_by(Vehicle.last_seen.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    vehicles = result.scalars().all()
    return [
        {
            "id": str(v.id),
            "plate_text": v.plate_text,
            "vehicle_type": v.vehicle_type,
            "color": v.color,
            "camera_id": v.camera_id,
            "last_seen": v.last_seen.isoformat() if v.last_seen else None,
        }
        for v in vehicles
    ]


# ===== ZONES =====

class ZoneCreate(BaseModel):
    zone_id: str
    name: str
    zone_type: str = "general"
    polygon: List[List[float]]  # [[x,y], ...]
    floor: int = 0
    camera_ids: Optional[List[str]] = None
    max_dwell_seconds: float = 300.0
    max_crowd: int = 20
    extra_metadata: Optional[dict] = None


class ZoneUpdate(BaseModel):
    name: Optional[str] = None
    zone_type: Optional[str] = None
    polygon: Optional[List[List[float]]] = None
    camera_ids: Optional[List[str]] = None
    max_dwell_seconds: Optional[float] = None
    max_crowd: Optional[int] = None
    extra_metadata: Optional[dict] = None


@router.post("/zones", tags=["Zones"])
async def create_zone(
    data: ZoneCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a geospatial zone."""
    existing = await db.execute(select(ZoneRecord).where(ZoneRecord.zone_id == data.zone_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Zone ID already exists")

    zone = ZoneRecord(
        zone_id=data.zone_id,
        name=data.name,
        zone_type=data.zone_type,
        polygon=data.polygon,
        floor=data.floor,
        camera_ids=data.camera_ids or [],
        max_dwell_seconds=data.max_dwell_seconds,
        max_crowd=data.max_crowd,
        created_at=datetime.utcnow(),
        extra_metadata=data.extra_metadata,
    )
    db.add(zone)
    await db.commit()
    await db.refresh(zone)
    return {
        "id": str(zone.id),
        "zone_id": zone.zone_id,
        "name": zone.name,
        "zone_type": zone.zone_type,
    }


@router.get("/zones", tags=["Zones"])
async def list_zones(
    db: AsyncSession = Depends(get_db),
    zone_type: Optional[str] = None,
    floor: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List zones with optional filters."""
    query = select(ZoneRecord)
    if zone_type:
        query = query.where(ZoneRecord.zone_type == zone_type)
    if floor is not None:
        query = query.where(ZoneRecord.floor == floor)
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    zones = result.scalars().all()
    return [
        {
            "id": str(z.id),
            "zone_id": z.zone_id,
            "name": z.name,
            "zone_type": z.zone_type,
            "polygon": z.polygon,
            "floor": z.floor,
            "camera_ids": z.camera_ids,
            "max_dwell_seconds": z.max_dwell_seconds,
            "max_crowd": z.max_crowd,
        }
        for z in zones
    ]


@router.get("/zones/{zone_id}", tags=["Zones"])
async def get_zone(zone_id: str, db: AsyncSession = Depends(get_db)):
    """Get a zone by its ID."""
    result = await db.execute(select(ZoneRecord).where(ZoneRecord.zone_id == zone_id))
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return {
        "id": str(zone.id),
        "zone_id": zone.zone_id,
        "name": zone.name,
        "zone_type": zone.zone_type,
        "polygon": zone.polygon,
        "floor": zone.floor,
        "camera_ids": zone.camera_ids,
        "max_dwell_seconds": zone.max_dwell_seconds,
        "max_crowd": zone.max_crowd,
        "created_at": zone.created_at.isoformat() if zone.created_at else None,
        "extra_metadata": zone.extra_metadata,
    }


@router.put("/zones/{zone_id}", tags=["Zones"])
async def update_zone(
    zone_id: str,
    data: ZoneUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.OPERATOR)),
):
    """Update a zone configuration."""
    result = await db.execute(select(ZoneRecord).where(ZoneRecord.zone_id == zone_id))
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    for field_name in ["name", "zone_type", "polygon", "camera_ids", "max_dwell_seconds", "max_crowd", "extra_metadata"]:
        val = getattr(data, field_name, None)
        if val is not None:
            setattr(zone, field_name, val)

    await db.commit()
    return {"status": "updated", "zone_id": zone_id}


@router.delete("/zones/{zone_id}", tags=["Zones"])
async def delete_zone(
    zone_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Delete a zone."""
    result = await db.execute(select(ZoneRecord).where(ZoneRecord.zone_id == zone_id))
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    await db.delete(zone)
    await db.commit()
    return {"status": "deleted", "zone_id": zone_id}


@router.get("/zones/{zone_id}/occupancy", tags=["Zones"])
async def zone_occupancy(
    zone_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get current track count in a zone (from active tracks)."""
    zone_result = await db.execute(select(ZoneRecord).where(ZoneRecord.zone_id == zone_id))
    zone = zone_result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    # Count active tracks whose last-known camera matches zone cameras
    camera_ids = zone.camera_ids or []
    if camera_ids:
        count_query = (
            select(func.count(Track.id))
            .where(Track.is_active == True, Track.camera_id.in_(camera_ids))
        )
    else:
        count_query = select(func.count(Track.id)).where(Track.is_active == True)

    count_result = await db.execute(count_query)
    count = count_result.scalar() or 0

    return {
        "zone_id": zone_id,
        "name": zone.name,
        "occupancy": count,
        "max_crowd": zone.max_crowd,
    }


# ===== KNOWLEDGE GRAPH =====

class RelationshipCreate(BaseModel):
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    relation_type: str
    weight: float = 1.0
    properties: Optional[dict] = None


@router.post("/graph/relationships", tags=["Knowledge Graph"])
async def create_relationship(
    data: RelationshipCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create an entity relationship edge."""
    rel = EntityRelationship(
        source_type=data.source_type,
        source_id=data.source_id,
        target_type=data.target_type,
        target_id=data.target_id,
        relation_type=data.relation_type,
        weight=data.weight,
        timestamp=datetime.utcnow(),
        properties=data.properties,
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return {
        "id": str(rel.id),
        "source": f"{rel.source_type}:{rel.source_id}",
        "target": f"{rel.target_type}:{rel.target_id}",
        "relation_type": rel.relation_type,
    }


@router.get("/graph/relationships", tags=["Knowledge Graph"])
async def list_relationships(
    db: AsyncSession = Depends(get_db),
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    target_type: Optional[str] = None,
    relation_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List entity relationships with optional filters."""
    query = select(EntityRelationship).order_by(EntityRelationship.timestamp.desc())
    if source_type:
        query = query.where(EntityRelationship.source_type == source_type)
    if source_id:
        query = query.where(EntityRelationship.source_id == source_id)
    if target_type:
        query = query.where(EntityRelationship.target_type == target_type)
    if relation_type:
        query = query.where(EntityRelationship.relation_type == relation_type)
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    rels = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "source": f"{r.source_type}:{r.source_id}",
            "target": f"{r.target_type}:{r.target_id}",
            "relation_type": r.relation_type,
            "weight": r.weight,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "properties": r.properties,
        }
        for r in rels
    ]


@router.get("/graph/entity/{entity_type}/{entity_id}/links", tags=["Knowledge Graph"])
async def get_entity_links(
    entity_type: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    relation_type: Optional[str] = None,
    limit: int = 100,
):
    """Get all relationships for a specific entity (both directions)."""
    outgoing_q = select(EntityRelationship).where(
        EntityRelationship.source_type == entity_type,
        EntityRelationship.source_id == entity_id,
    )
    incoming_q = select(EntityRelationship).where(
        EntityRelationship.target_type == entity_type,
        EntityRelationship.target_id == entity_id,
    )
    if relation_type:
        outgoing_q = outgoing_q.where(EntityRelationship.relation_type == relation_type)
        incoming_q = incoming_q.where(EntityRelationship.relation_type == relation_type)

    outgoing_q = outgoing_q.limit(limit)
    incoming_q = incoming_q.limit(limit)

    out_result = await db.execute(outgoing_q)
    in_result = await db.execute(incoming_q)

    outgoing = out_result.scalars().all()
    incoming = in_result.scalars().all()

    return {
        "entity": f"{entity_type}:{entity_id}",
        "outgoing": [
            {
                "target": f"{r.target_type}:{r.target_id}",
                "relation_type": r.relation_type,
                "weight": r.weight,
            }
            for r in outgoing
        ],
        "incoming": [
            {
                "source": f"{r.source_type}:{r.source_id}",
                "relation_type": r.relation_type,
                "weight": r.weight,
            }
            for r in incoming
        ],
        "total_links": len(outgoing) + len(incoming),
    }


@router.get("/graph/stats", tags=["Knowledge Graph"])
async def graph_stats(db: AsyncSession = Depends(get_db)):
    """Return knowledge graph statistics."""
    total = await db.execute(select(func.count(EntityRelationship.id)))
    total_count = total.scalar() or 0

    type_counts = await db.execute(
        select(
            EntityRelationship.relation_type,
            func.count(EntityRelationship.id),
        ).group_by(EntityRelationship.relation_type)
    )
    by_type = {r[0]: r[1] for r in type_counts.all()}

    entity_counts = await db.execute(
        select(
            EntityRelationship.source_type,
            func.count(func.distinct(EntityRelationship.source_id)),
        ).group_by(EntityRelationship.source_type)
    )
    by_entity = {r[0]: r[1] for r in entity_counts.all()}

    return {
        "total_relationships": total_count,
        "by_relation_type": by_type,
        "unique_entities_by_type": by_entity,
    }


@router.get("/audit/logs", tags=["Audit"])
async def get_audit_logs(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """Return recent administrative audit records without exposing password material."""
    limit = max(1, min(limit, 500))
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    )
    return [
        {
            "id": str(row.id),
            "user_id": str(row.user_id) if row.user_id else None,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "timestamp": row.timestamp.isoformat(),
            "ip_address": row.ip_address,
            "details": row.details,
        }
        for row in result.scalars().all()
    ]
