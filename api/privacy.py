"""Privacy and data-subject lifecycle endpoints."""

from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, require_role
from db.models import (
    AuditLog,
    EntityRelationship,
    Incident,
    IncidentEvent,
    Pattern,
    Person,
    Sighting,
    UserRole,
)

router = APIRouter(prefix="/privacy", tags=["Privacy & Compliance"])
_real_get_db = None


async def get_db():
    if _real_get_db is None:
        raise RuntimeError("Database dependency not configured")
    async for session in _real_get_db():
        yield session


@router.delete("/persons/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_person(
    person_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """Permanently remove a person and directly associated intelligence records."""
    person = await db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    # Preserve a non-identifying administrative audit record while removing
    # the subject's operational data.
    db.add(
        AuditLog(
            user_id=UUID(user["id"]),
            action="privacy_forget_person",
            resource_type="person",
            resource_id=str(person_id),
            details={"performed_by": user.get("username")},
        )
    )

    await db.execute(delete(IncidentEvent).where(IncidentEvent.sighting_id.in_(
        select(Sighting.id).where(Sighting.person_id == person_id)
    )))
    await db.execute(delete(Sighting).where(Sighting.person_id == person_id))
    await db.execute(delete(Pattern).where(Pattern.person_id == person_id))
    await db.execute(delete(Incident).where(Incident.person_id == person_id))
    await db.execute(
        delete(EntityRelationship).where(
            (EntityRelationship.source_type == "person")
            & (EntityRelationship.source_id == str(person_id))
            | (EntityRelationship.target_type == "person")
            & (EntityRelationship.target_id == str(person_id))
        )
    )
    await db.delete(person)
    await db.commit()
    return None


@router.post("/retention/purge", tags=["Privacy & Compliance"])
async def purge_expired_unknown_sightings(
    retention_days: int = 90,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """Delete unknown sightings older than the configured retention period."""
    if retention_days < 1 or retention_days > 3650:
        raise HTTPException(status_code=400, detail="retention_days must be between 1 and 3650")

    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    result = await db.execute(
        delete(Sighting)
        .where(Sighting.person_id.is_(None), Sighting.timestamp < cutoff)
    )
    deleted = result.rowcount or 0
    db.add(
        AuditLog(
            user_id=UUID(user["id"]),
            action="privacy_retention_purge",
            resource_type="sighting",
            details={"retention_days": retention_days, "deleted": deleted},
        )
    )
    await db.commit()
    return {"status": "purged", "deleted": deleted, "cutoff": cutoff.isoformat()}


@router.get("/policy", tags=["Privacy & Compliance"])
async def privacy_policy_metadata():
    """Machine-readable defaults used by the application privacy controls."""
    return {
        "unknown_sighting_retention_days": 90,
        "person_deletion": "permanent",
        "audit_deletion_events": "retained",
        "embedding_storage": "application-controlled",
    }
