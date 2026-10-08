"""
Database models for SentinelForge.
Supports PostgreSQL (with TimescaleDB/pgvector) and SQLite (dev mode).
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON, Enum as SQLEnum, TypeDecorator
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

# --- Portable UUID and vector types -----------------------------------------

class PortableUUID(TypeDecorator):
    """Platform-agnostic UUID: native UUID on PostgreSQL, CHAR(36) elsewhere."""
    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PGUUID
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value if isinstance(value, UUID) else UUID(str(value))


try:
    from pgvector.sqlalchemy import Vector as _PGVector
except ImportError:
    _PGVector = None


class PortableVector(TypeDecorator):
    """pgvector on PostgreSQL; JSON text on SQLite/development databases."""
    impl = Text
    cache_ok = True

    def __init__(self, dimensions: int):
        self.dimensions = dimensions
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and _PGVector is not None:
            return dialect.type_descriptor(_PGVector(self.dimensions))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        import json
        return json.dumps(list(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        import json
        return json.loads(value) if isinstance(value, str) else value


def VectorColumn(dim: int):
    return Column(PortableVector(dim))


Base = declarative_base()

# Alias used throughout
PGUUID = PortableUUID


# Enums
class UserRole(enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class CameraType(enum.Enum):
    IP_WEBCAM = "ip_webcam"
    RTSP = "rtsp"
    USB = "usb"
    FILE = "file"
    HTTP = "http"


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

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    role = Column(String(100))
    details = Column(JSON)
    embedding = VectorColumn(128)  # 128-dimensional face embedding
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

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    person_id = Column(PortableUUID(), ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    camera_id = Column(String(100), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    embedding = VectorColumn(128)  # Encrypted in application layer
    face_image_b64 = Column(Text)
    flag_level = Column(Integer, default=0, nullable=False)  # 0=normal, 1=repeat, 2=high_risk, 3=critical
    extra_metadata = Column(JSON)  # pose, lighting, etc.

    # Relationships
    person = relationship("Person", back_populates="sightings")
    footage_refs = relationship("FootageRef", back_populates="sighting")


class Pattern(Base):
    __tablename__ = "patterns"

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    person_id = Column(PortableUUID(), ForeignKey("persons.id", ondelete="CASCADE"), nullable=True)
    date = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    pattern_type = Column(String(50))
    confidence = Column(Float)
    sighting_count = Column(Integer, default=0)
    avg_duration = Column(Float)
    anomaly_score = Column(Float, default=0.0)
    metadata_json = Column("metadata", JSON)
    detected_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    person = relationship("Person", back_populates="patterns")


class FootageRef(Base):
    __tablename__ = "footage_refs"

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    sighting_id = Column(PortableUUID(), ForeignKey("sightings.id", ondelete="CASCADE"), nullable=False)
    video_path = Column(String(500), nullable=False)
    start_frame = Column(Integer, nullable=False)
    duration = Column(Integer)  # Duration in frames

    # Relationships
    sighting = relationship("Sighting", back_populates="footage_refs")


class User(Base):
    __tablename__ = "users"

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
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

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    camera_id = Column(String(100), unique=True, nullable=False, index=True)
    camera_type = Column(SQLEnum(CameraType), default=CameraType.IP_WEBCAM, nullable=False)
    stream_url = Column(String(500), nullable=False)  # IP Webcam URL / RTSP / device index
    snapshot_url = Column(String(500))  # Optional snapshot endpoint (auto-derived for IP Webcam)
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

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    sighting_id = Column(PortableUUID(), ForeignKey("sightings.id", ondelete="CASCADE"))
    alert_type = Column(String(50), nullable=False)  # unknown, repeat_offender, anomaly
    severity = Column(Integer, default=1, nullable=False)  # 1=low, 2=medium, 3=high, 4=critical
    status = Column(SQLEnum(AlertStatus), default=AlertStatus.NEW, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    acknowledged_at = Column(DateTime)
    assigned_to = Column(PortableUUID(), ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at = Column(DateTime)
    notes = Column(Text)
    extra_metadata = Column(JSON)

    # Relationships
    sighting = relationship("Sighting")
    assigned_to_user = relationship("User", back_populates="alerts")


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    person_id = Column(PortableUUID(), ForeignKey("persons.id", ondelete="SET NULL"))
    camera_id = Column(PortableUUID(), ForeignKey("cameras.id", ondelete="SET NULL"))
    status = Column(SQLEnum(IncidentStatus), default=IncidentStatus.OPEN, nullable=False)
    severity = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_by = Column(PortableUUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    assigned_to = Column(PortableUUID(), ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at = Column(DateTime)
    extra_metadata = Column(JSON)

    # Relationships
    person = relationship("Person", back_populates="incidents")
    camera = relationship("Camera", back_populates="incidents")
    incident_events = relationship("IncidentEvent", back_populates="incident")


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    incident_id = Column(PortableUUID(), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)
    sighting_id = Column(PortableUUID(), ForeignKey("sightings.id", ondelete="SET NULL"))
    event_type = Column(String(50), nullable=False)  # sighting, note, status_change
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(PortableUUID(), ForeignKey("users.id", ondelete="SET NULL"))
    extra_metadata = Column(JSON)

    # Relationships
    incident = relationship("Incident", back_populates="incident_events")
    sighting = relationship("Sighting")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    user_id = Column(PortableUUID(), ForeignKey("users.id", ondelete="SET NULL"))
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

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    user_id = Column(PortableUUID(), ForeignKey("users.id", ondelete="SET NULL"))
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

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    sighting_id = Column(PortableUUID(), ForeignKey("sightings.id", ondelete="SET NULL"), nullable=True)
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

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
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

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    behavior_type = Column(String(50), nullable=False, index=True)
    severity = Column(Integer, default=1, nullable=False)
    track_id = Column(String(100), index=True)
    camera_id = Column(String(100), index=True)
    zone_id = Column(String(100), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    description = Column(Text)
    extra_metadata = Column(JSON)


# ===== VEHICLE TABLE =====

class Vehicle(Base):
    """Stores vehicle intelligence results (type, color, plate)."""

    __tablename__ = "vehicles"

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
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

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
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

    id = Column(PortableUUID(), primary_key=True, default=uuid4)
    source_type = Column(String(50), nullable=False, index=True)
    source_id = Column(String(255), nullable=False, index=True)
    target_type = Column(String(50), nullable=False, index=True)
    target_id = Column(String(255), nullable=False, index=True)
    relation_type = Column(String(50), nullable=False, index=True)
    weight = Column(Float, default=1.0)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    properties = Column(JSON)

