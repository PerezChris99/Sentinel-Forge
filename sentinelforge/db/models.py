"""
Database models for SentinelForge.
Requires PostgreSQL with TimescaleDB and pgvector extensions.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import enum

Base = declarative_base()


# Enums
class UserRole(enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class CameraStatus(enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    DISABLED = "disabled"


class IncidentStatus(enum.Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    CLOSED = "closed"


class AlertStatus(enum.Enum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    ESCALATED = "escalated"


class Person(Base):
    __tablename__ = "persons"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    role = Column(String(100))
    details = Column(JSON)
    embedding = Column(Vector(128))  # 128-dimensional face embedding
    known_status = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    consent_given = Column(Boolean, default=False, nullable=False)
    notes = Column(Text)  # Additional notes
    photo_urls = Column(JSON)  # Array of photo URLs
    is_archived = Column(Boolean, default=False, nullable=False)

    # Relationships
    sightings = relationship("Sighting", back_populates="person")
    patterns = relationship("Pattern", back_populates="person")
    incidents = relationship("Incident", back_populates="person")


class Sighting(Base):
    __tablename__ = "sightings"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    person_id = Column(PGUUID(as_uuid=True), ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    camera_id = Column(String(100), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    embedding = Column(Vector(128))  # Encrypted in application layer
    face_image_b64 = Column(Text)
    flag_level = Column(Integer, default=0, nullable=False)  # 0=normal, 1=repeat, 2=high_risk, 3=critical
    extra_metadata = Column(JSON)  # pose, lighting, etc.

    # Relationships
    person = relationship("Person", back_populates="sightings")
    footage_refs = relationship("FootageRef", back_populates="sighting")


class Pattern(Base):
    __tablename__ = "patterns"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    person_id = Column(PGUUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    date = Column(DateTime, nullable=False, index=True)
    sighting_count = Column(Integer, default=0)
    avg_duration = Column(Float)  # Average duration in seconds
    anomaly_score = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    person = relationship("Person", back_populates="patterns")


class FootageRef(Base):
    __tablename__ = "footage_refs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    sighting_id = Column(PGUUID(as_uuid=True), ForeignKey("sightings.id", ondelete="CASCADE"), nullable=False)
    video_path = Column(String(500), nullable=False)
    start_frame = Column(Integer, nullable=False)
    duration = Column(Integer)  # Duration in frames

    # Relationships
    sighting = relationship("Sighting", back_populates="footage_refs")


class User(Base):
    __tablename__ = "users"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.VIEWER, nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime)
    extra_metadata = Column(JSON)

    # Relationships
    audit_logs = relationship("AuditLog", back_populates="user")
    alerts = relationship("Alert", back_populates="assigned_to_user")


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    camera_id = Column(String(100), unique=True, nullable=False, index=True)
    stream_url = Column(String(500), nullable=False)  # IP Webcam URL
    location = Column(String(255))
    zone = Column(String(100))
    status = Column(SQLEnum(CameraStatus), default=CameraStatus.OFFLINE, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime)
    extra_metadata = Column(JSON)  # Resolution, FPS, coverage area
    
    # Relationships
    incidents = relationship("Incident", back_populates="camera")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    sighting_id = Column(PGUUID(as_uuid=True), ForeignKey("sightings.id", ondelete="CASCADE"))
    alert_type = Column(String(50), nullable=False)  # unknown, repeat_offender, anomaly
    severity = Column(Integer, default=1, nullable=False)  # 1=low, 2=medium, 3=high, 4=critical
    status = Column(SQLEnum(AlertStatus), default=AlertStatus.NEW, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    acknowledged_at = Column(DateTime)
    assigned_to = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at = Column(DateTime)
    notes = Column(Text)
    extra_metadata = Column(JSON)

    # Relationships
    sighting = relationship("Sighting")
    assigned_to_user = relationship("User", back_populates="alerts")


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    person_id = Column(PGUUID(as_uuid=True), ForeignKey("persons.id", ondelete="SET NULL"))
    camera_id = Column(PGUUID(as_uuid=True), ForeignKey("cameras.id", ondelete="SET NULL"))
    status = Column(SQLEnum(IncidentStatus), default=IncidentStatus.OPEN, nullable=False)
    severity = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    assigned_to = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at = Column(DateTime)
    extra_metadata = Column(JSON)

    # Relationships
    person = relationship("Person", back_populates="incidents")
    camera = relationship("Camera", back_populates="incidents")
    incident_events = relationship("IncidentEvent", back_populates="incident")


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    incident_id = Column(PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)
    sighting_id = Column(PGUUID(as_uuid=True), ForeignKey("sightings.id", ondelete="SET NULL"))
    event_type = Column(String(50), nullable=False)  # sighting, note, status_change
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    extra_metadata = Column(JSON)

    # Relationships
    incident = relationship("Incident", back_populates="incident_events")
    sighting = relationship("Sighting")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action = Column(String(100), nullable=False)  # login, view_person, delete_sighting
    resource_type = Column(String(50))  # person, sighting, incident
    resource_id = Column(String(255))
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    details = Column(JSON)

    # Relationships
    user = relationship("User", back_populates="audit_logs")


class SearchQuery(Base):
    __tablename__ = "search_queries"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    query_text = Column(Text, nullable=False)
    filters = Column(JSON)
    result_count = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    execution_time_ms = Column(Float)



class DetectedObject(Base):
    """Stores per-frame / per-sighting object detections (non-face objects).

    This table is purposefully lightweight and intended to store detection
    metadata that can be joined with `sightings` for richer context.
    """

    __tablename__ = "detected_objects"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    sighting_id = Column(PGUUID(as_uuid=True), ForeignKey("sightings.id", ondelete="SET NULL"), nullable=True)
    track_id = Column(String(100), index=True)
    object_class = Column(String(100), nullable=False)
    confidence = Column(Float, default=0.0)
    bbox = Column(JSON)  # [x1,y1,x2,y2]
    camera_id = Column(String(100), nullable=False, index=True)
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    extra_metadata = Column(JSON)

    # Relationships
    sighting = relationship("Sighting")


class Track(Base):
    """High-level track entity aggregating detections into a persistent track.

    Tracks can represent a single moving object across frames and optionally
    across cameras (when tracking IDs are reconciled).
    """

    __tablename__ = "tracks"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    track_label = Column(String(100), unique=True, nullable=False, index=True)
    camera_id = Column(String(100), index=True)
    object_class = Column(String(100))
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    extra_metadata = Column(JSON)

    # Convenience relationship: detected objects linked by track_id string
    detected_objects = relationship("DetectedObject", primaryjoin="Track.track_label==foreign(DetectedObject.track_id)")


# ===== BEHAVIOR EVENTS TABLE =====

class BehaviorEventRecord(Base):
    """Stores behavior analysis events (loitering, intrusion, crowd, etc.)."""

    __tablename__ = "behavior_events"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    behavior_type = Column(String(50), nullable=False, index=True)
    severity = Column(Integer, default=1, nullable=False)
    track_id = Column(String(100), index=True)
    camera_id = Column(String(100), index=True)
    zone_id = Column(String(100), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    description = Column(Text)
    metadata = Column(JSON)


# ===== VEHICLE TABLE =====

class Vehicle(Base):
    """Stores vehicle intelligence results (type, color, plate)."""

    __tablename__ = "vehicles"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    track_id = Column(String(100), index=True)
    vehicle_type = Column(String(50), nullable=False)
    color = Column(String(30))
    plate_text = Column(String(20), index=True)
    plate_confidence = Column(Float)
    camera_id = Column(String(100), index=True)
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    extra_metadata = Column(JSON)


# ===== ZONE TABLE =====

class ZoneRecord(Base):
    """Persistent storage for geospatial zones."""

    __tablename__ = "zones"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    zone_id = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    zone_type = Column(String(50), default="general")
    polygon = Column(JSON, nullable=False)   # [[x,y], ...]
    floor = Column(Integer, default=0)
    camera_ids = Column(JSON)  # ["cam1", "cam2"]
    max_dwell_seconds = Column(Float, default=300.0)
    max_crowd = Column(Integer, default=20)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    extra_metadata = Column(JSON)


# ===== ENTITY RELATIONSHIP TABLE (Knowledge Graph) =====

class EntityRelationship(Base):
    """Stores typed edges between any two entities for knowledge graph analysis."""

    __tablename__ = "entity_relationships"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_type = Column(String(50), nullable=False, index=True)
    source_id = Column(String(255), nullable=False, index=True)
    target_type = Column(String(50), nullable=False, index=True)
    target_id = Column(String(255), nullable=False, index=True)
    relation_type = Column(String(50), nullable=False, index=True)
    weight = Column(Float, default=1.0)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    properties = Column(JSON)

