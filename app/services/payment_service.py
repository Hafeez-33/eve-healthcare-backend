import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.enums import BookingStatus, PaymentStatus
from app.models.payment import Payment
from app.models.webhook_event import WebhookEvent
from app.schemas.payment import PaymentCreate, WebhookPayload


def create_simulated_payment(
    db: Session,
    user_id: uuid.UUID,
    data: PaymentCreate,
) -> Payment:
    """Create a simulated payment for a booking with row-level locking and status transition."""
    # 1. Lock the booking row for update
    booking = db.scalar(
        select(Booking)
        .where(Booking.id == data.booking_id)
        .with_for_update()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    # 2. Enforce tenancy ownership
    if booking.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this booking is forbidden",
        )

    # 3. Verify booking is in PENDING state
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot pay for booking with status {booking.status.value}",
        )

    # 4. Snapshot amount directly from booking.amount (immutable historical price)
    amount = booking.amount

    # 5. Generate a unique transaction reference
    transaction_reference = f"TXN_SIM_{uuid.uuid4().hex[:12].upper()}"

    # 6. Instantiate Payment record
    payment = Payment(
        booking_id=booking.id,
        transaction_reference=transaction_reference,
        amount=amount,
        status=data.simulate_status,
        payment_method="SIMULATED",
    )
    db.add(payment)

    # 7. Apply booking state machine transition
    if data.simulate_status == PaymentStatus.SUCCESS:
        booking.status = BookingStatus.CONFIRMED
    else:
        booking.status = BookingStatus.FAILED

    # 8. Commit atomic transaction
    try:
        db.commit()
        db.refresh(payment)
        return payment
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transaction reference conflict occurred",
        )
    except Exception:
        db.rollback()
        raise


def process_webhook(
    db: Session,
    payload: WebhookPayload,
) -> dict:
    """Process an incoming payment gateway webhook with atomic idempotency and row locking."""
    # 1. Atomically insert webhook event using PostgreSQL ON CONFLICT DO NOTHING
    stmt = (
        pg_insert(WebhookEvent)
        .values(
            event_id=payload.event_id,
            event_type=payload.event_type,
            booking_id=payload.data.booking_id,
            payload=payload.model_dump(mode="json"),
            processed_at=func.now(),
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(WebhookEvent.id)
    )

    try:
        result = db.execute(stmt)
        inserted_id = result.scalar_one_or_none()
    except IntegrityError:
        # Foreign key violation on booking_id
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    # 2. Check for duplicate event_id (idempotency key)
    if inserted_id is None:
        db.rollback()
        return {
            "status": "already_processed",
            "event_id": payload.event_id,
        }

    # 3. Lock booking row for update
    booking = db.scalar(
        select(Booking)
        .where(Booking.id == payload.data.booking_id)
        .with_for_update()
    )
    if not booking:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    # 4. Protect against amount discrepancies
    if payload.data.amount != booking.amount:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AMOUNT_MISMATCH: Payment amount does not match booking amount",
        )

    # 5. Check and record or update payment record
    existing_payment = db.scalar(
        select(Payment)
        .where(Payment.transaction_reference == payload.data.transaction_reference)
        .with_for_update()
    )
    if not existing_payment:
        payment = Payment(
            booking_id=booking.id,
            transaction_reference=payload.data.transaction_reference,
            amount=payload.data.amount,
            status=payload.data.status,
            payment_method="SIMULATED",
        )
        db.add(payment)
    else:
        existing_payment.status = payload.data.status

    # 6. Apply state machine transition if booking is still PENDING
    if booking.status == BookingStatus.PENDING:
        if payload.data.status == PaymentStatus.SUCCESS:
            booking.status = BookingStatus.CONFIRMED
        elif payload.data.status == PaymentStatus.FAILED:
            booking.status = BookingStatus.FAILED
    # If booking is already in a terminal state (CONFIRMED, FAILED, CANCELLED),
    # its state remains unchanged.

    # 7. Update processed_at and commit atomic transaction
    db.execute(
        update(WebhookEvent)
        .where(WebhookEvent.id == inserted_id)
        .values(processed_at=func.now())
    )

    try:
        db.commit()
        return {
            "status": "processed",
            "event_id": payload.event_id,
            "booking_status": booking.status.value,
        }
    except Exception:
        db.rollback()
        raise
