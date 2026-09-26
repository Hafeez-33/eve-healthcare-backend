import uuid
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingResponse
from app.services.booking_service import (
    cancel_user_booking,
    create_booking,
    get_user_booking,
    list_user_bookings,
)

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.post(
    "/",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new diagnostic test booking",
)
def create_new_booking(
    data: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Book a diagnostic test at a centre. Captures current test price as immutable amount."""
    return create_booking(db, user_id=current_user.id, data=data)


@router.get(
    "/",
    response_model=List[BookingResponse],
    status_code=status.HTTP_200_OK,
    summary="List authenticated user's bookings",
)
def get_user_bookings(
    skip: int = Query(0, ge=0, description="Pagination skip offset"),
    limit: int = Query(100, ge=1, le=100, description="Pagination limit"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all bookings belonging to the currently authenticated user."""
    return list_user_bookings(db, user_id=current_user.id, skip=skip, limit=limit)


@router.get(
    "/{id}",
    response_model=BookingResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single booking details",
)
def get_booking_details(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve details of a specific booking. Enforces cross-user tenancy isolation."""
    return get_user_booking(db, booking_id=id, user_id=current_user.id)


@router.patch(
    "/{id}/cancel",
    response_model=BookingResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel a pending booking",
)
def cancel_booking(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a pending booking owned by the authenticated user."""
    return cancel_user_booking(db, booking_id=id, user_id=current_user.id)
