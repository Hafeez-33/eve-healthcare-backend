import uuid
from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.diagnostic_centre import DiagnosticCentre
from app.schemas.centre import CentreCreate


def list_centres(db: Session, skip: int = 0, limit: int = 100) -> List[DiagnosticCentre]:
    """Retrieve all diagnostic centres with their offered diagnostic tests."""
    stmt = (
        select(DiagnosticCentre)
        .options(selectinload(DiagnosticCentre.diagnostic_tests))
        .order_by(DiagnosticCentre.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def get_centre_by_id(db: Session, centre_id: uuid.UUID) -> DiagnosticCentre:
    """Retrieve a single diagnostic centre by ID along with its tests."""
    stmt = (
        select(DiagnosticCentre)
        .options(selectinload(DiagnosticCentre.diagnostic_tests))
        .where(DiagnosticCentre.id == centre_id)
    )
    centre = db.scalar(stmt)
    if not centre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnostic centre not found",
        )
    return centre


def create_centre(db: Session, data: CentreCreate) -> DiagnosticCentre:
    """Create a new diagnostic centre."""
    centre = DiagnosticCentre(
        name=data.name,
        location=data.location,
        contact_number=data.contact_number,
    )
    db.add(centre)
    db.commit()
    db.refresh(centre)
    return centre
