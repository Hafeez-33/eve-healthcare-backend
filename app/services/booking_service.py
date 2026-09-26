import uuid
from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.diagnostic_centre import DiagnosticCentre
from app.models.diagnostic_test import DiagnosticTest
from app.models.enums import BookingStatus
from app.schemas.booking import BookingCreate

# Strict Booking State Machine transitions
ALLOWED_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.PENDING: {
        BookingStatus.CONFIRMED,
        BookingStatus.FAILED,
        BookingStatus.CANCELLED,
    },
    BookingStatus.CONFIRMED: set(),
    BookingStatus.FAILED: set(),
    BookingStatus.CANCELLED: set(),
}


def create_booking(
    db: Session,
    user_id: uuid.UUID,
    data: BookingCreate,
) -> Booking:
    """Create a new diagnostic test booking with price snapshot and validation."""
    # 1. Validate that the diagnostic centre exists
    centre = db.scalar(select(DiagnosticCentre).where(DiagnosticCentre.id == data.centre_id))
    if not centre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnostic centre not found",
        )

    # 2. Validate that the diagnostic test exists
    test = db.scalar(select(DiagnosticTest).where(DiagnosticTest.id == data.test_id))
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnostic test not found",
        )

    # 3. Validate that the diagnostic test belongs to the specified centre
    if test.centre_id != data.centre_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Diagnostic test does not belong to the specified centre",
        )

    # 4. Validate that the diagnostic test is active
    if not test.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Diagnostic test is not currently active",
        )

    # 5. Snapshot test price at booking time (historical immutable snapshot)
    amount = test.price

    # 6. Instantiate booking with PENDING status
    booking = Booking(
        user_id=user_id,
        centre_id=data.centre_id,
        test_id=data.test_id,
        appointment_datetime=data.appointment_datetime,
        amount=amount,
        status=BookingStatus.PENDING,
    )
    db.add(booking)

    try:
        db.commit()
        db.refresh(booking)
        return booking
    except Exception:
        db.rollback()
        raise


def list_user_bookings(
    db: Session,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> List[Booking]:
    """Retrieve all bookings belonging to the authenticated user."""
    stmt = (
        select(Booking)
        .where(Booking.user_id == user_id)
        .order_by(Booking.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def get_user_booking(
    db: Session,
    booking_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Booking:
    """Retrieve a specific booking, enforcing tenant ownership."""
    booking = db.scalar(select(Booking).where(Booking.id == booking_id))
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if booking.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this booking is forbidden",
        )

    return booking


def transition_booking_status(
    db: Session,
    booking: Booking,
    new_status: BookingStatus,
) -> Booking:
    """Validate and execute a state transition in the booking state machine."""
    if isinstance(new_status, str):
        new_status = BookingStatus(new_status)

    allowed = ALLOWED_TRANSITIONS.get(booking.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition booking from {booking.status.value} to {new_status.value}",
        )

    booking.status = new_status
    try:
        db.commit()
        db.refresh(booking)
        return booking
    except Exception:
        db.rollback()
        raise


def cancel_user_booking(
    db: Session,
    booking_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Booking:
    """Cancel a pending booking owned by the authenticated user."""
    booking = get_user_booking(db, booking_id=booking_id, user_id=user_id)
    return transition_booking_status(db, booking, BookingStatus.CANCELLED)
