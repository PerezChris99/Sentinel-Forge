"""
Extended API endpoints for authentication, camera management, alerts, incidents, and search
"""
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID
import base64

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Request
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
import face_recognition  # Optional - only needed for photo upload
import numpy as np

from db.models import (
    User, UserRole, Camera, CameraStatus, Alert, AlertStatus,
    Incident, IncidentStatus, IncidentEvent, Person, Sighting,
    AuditLog, SearchQuery
)
from api.auth import (
    get_current_user, require_role, get_password_hash,
    verify_password, create_access_token
)


# DB Dependency (will be imported from main.py)
async def get_db():
    """Placeholder - will use main.py's get_db"""
    pass


# Router
router = APIRouter()


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
async def register(user_data: UserRegister, db: AsyncSession = Depends()):
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
    access_token = create_access_token(data={"sub": str(user.id), "username": user.username})
    
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
async def login(credentials: UserLogin, db: AsyncSession = Depends()):
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
    access_token = create_access_token(data={"sub": str(user.id), "username": user.username})
    
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
    stream_url: str  # IP Webcam URL
    location: Optional[str] = None
    zone: Optional[str] = None
    extra_metadata: Optional[dict] = {}


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    stream_url: Optional[str] = None
    location: Optional[str] = None
    zone: Optional[str] = None
    is_enabled: Optional[bool] = None
    extra_metadata: Optional[dict] = None


@router.post("/cameras", tags=["Cameras"])
async def create_camera(
    camera_data: CameraCreate,
    db: AsyncSession = Depends(),
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
    
    camera = Camera(
        name=camera_data.name,
        camera_id=camera_data.camera_id,
        stream_url=camera_data.stream_url,
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
        "stream_url": camera.stream_url,
        "location": camera.location,
        "zone": camera.zone,
        "status": camera.status.value,
        "is_enabled": camera.is_enabled
    }


@router.get("/cameras", tags=["Cameras"])
async def list_cameras(
    db: AsyncSession = Depends(),
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
async def get_camera(camera_id: str, db: AsyncSession = Depends()):
    """Get camera details"""
    result = await db.execute(select(Camera).where(Camera.camera_id == camera_id))
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    return {
        "id": str(camera.id),
        "name": camera.name,
        "camera_id": camera.camera_id,
        "stream_url": camera.stream_url,
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
    db: AsyncSession = Depends(),
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
        camera.stream_url = camera_data.stream_url
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
    db: AsyncSession = Depends(),
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
async def camera_heartbeat(camera_id: str, db: AsyncSession = Depends()):
    """Update camera last seen (heartbeat)"""
    result = await db.execute(select(Camera).where(Camera.camera_id == camera_id))
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    camera.last_seen = datetime.utcnow()
    camera.status = CameraStatus.ONLINE
    await db.commit()
    
    return {"status": "ok", "last_seen": camera.last_seen.isoformat()}


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
    db: AsyncSession = Depends(),
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
    db: AsyncSession = Depends(),
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
async def get_person(person_id: UUID, db: AsyncSession = Depends()):
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
    db: AsyncSession = Depends(),
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
    db: AsyncSession = Depends(),
    user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Upload a photo for a person and extract face embedding"""
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
    db: AsyncSession = Depends(),
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
    db: AsyncSession = Depends(),
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
    db: AsyncSession = Depends(),
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
    db: AsyncSession = Depends(),
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
    db: AsyncSession = Depends(),
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
    db: AsyncSession = Depends(),
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
    db: AsyncSession = Depends(),
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
async def get_incident(incident_id: UUID, db: AsyncSession = Depends()):
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
    db: AsyncSession = Depends(),
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
    db: AsyncSession = Depends(),
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
    db: AsyncSession = Depends(),
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
    db: AsyncSession = Depends(),
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
