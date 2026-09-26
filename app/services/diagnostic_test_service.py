import uuid
from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.diagnostic_centre import DiagnosticCentre
from app.models.diagnostic_test import DiagnosticTest
from app.schemas.diagnostic_test import DiagnosticTestCreate


def list_tests_by_centre(db: Session, centre_id: uuid.UUID) -> List[DiagnosticTest]:
    """Retrieve all diagnostic tests offered by a specific diagnostic centre."""
    centre = db.scalar(select(DiagnosticCentre).where(DiagnosticCentre.id == centre_id))
    if not centre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnostic centre not found",
        )

    stmt = (
        select(DiagnosticTest)
        .where(DiagnosticTest.centre_id == centre_id)
        .order_by(DiagnosticTest.name.asc())
    )
    return list(db.scalars(stmt).all())


def create_diagnostic_test(
    db: Session,
    centre_id: uuid.UUID,
    data: DiagnosticTestCreate,
) -> DiagnosticTest:
    """Create a diagnostic test under a specific centre with uniqueness and price validation."""
    centre = db.scalar(select(DiagnosticCentre).where(DiagnosticCentre.id == centre_id))
    if not centre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnostic centre not found",
        )

    # Pre-check for duplicate test name within the centre
    existing_test = db.scalar(
        select(DiagnosticTest).where(
            DiagnosticTest.centre_id == centre_id,
            DiagnosticTest.name == data.name,
        )
    )
    if existing_test:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Diagnostic test with this name already exists at this centre",
        )

    test = DiagnosticTest(
        centre_id=centre_id,
        name=data.name,
        description=data.description,
        price=data.price,
        is_active=True,
    )
    db.add(test)

    try:
        db.commit()
        db.refresh(test)
        return test
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Diagnostic test with this name already exists at this centre",
        )
