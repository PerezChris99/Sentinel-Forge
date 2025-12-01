"""
Database models for SentinelForge.
Requires PostgreSQL with TimescaleDB and pgvector extensions.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()


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

    # Relationships
    sightings = relationship("Sighting", back_populates="person")
    patterns = relationship("Pattern", back_populates="person")


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
    metadata = Column(JSON)  # pose, lighting, etc.

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
