import uuid
from decimal import Decimal
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.booking import Booking
from app.models.diagnostic_centre import DiagnosticCentre
from app.models.diagnostic_test import DiagnosticTest
from app.models.enums import BookingStatus, PaymentStatus
from app.models.payment import Payment
from app.models.user import User
from app.models.webhook_event import WebhookEvent


@pytest.fixture
def db():
    """Provides a transactional database session rolled back after test completion."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_centre_and_test_relationship(db):
    centre = DiagnosticCentre(
        name=f"Test Centre {uuid.uuid4().hex[:6]}",
        location="Indiranagar, Bangalore",
        contact_number="+919876543200",
    )
    db.add(centre)
    db.flush()

    test = DiagnosticTest(
        centre_id=centre.id,
        name="Liver Function Test",
        description="Assesses hepatic function",
        price=Decimal("750.00"),
        is_active=True,
    )
    db.add(test)
    db.flush()

    assert test in centre.diagnostic_tests
    assert test.centre.id == centre.id
    assert test.price == Decimal("750.00")


def test_duplicate_test_name_in_same_centre_rejected(db):
    centre = DiagnosticCentre(
        name=f"Test Centre {uuid.uuid4().hex[:6]}",
        location="Koramangala, Bangalore",
        contact_number="+919876543201",
    )
    db.add(centre)
    db.flush()

    test1 = DiagnosticTest(
        centre_id=centre.id,
        name="Urine Routine",
        price=Decimal("200.00"),
    )
    db.add(test1)
    db.flush()

    # Attempt to add duplicate test name in the same centre
    test2 = DiagnosticTest(
        centre_id=centre.id,
        name="Urine Routine",
        price=Decimal("250.00"),
    )
    db.add(test2)

    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_negative_test_price_rejected(db):
    centre = DiagnosticCentre(
        name=f"Test Centre {uuid.uuid4().hex[:6]}",
        location="Jayanagar, Bangalore",
        contact_number="+919876543202",
    )
    db.add(centre)
    db.flush()

    invalid_test = DiagnosticTest(
        centre_id=centre.id,
        name="Zero Price Test",
        price=Decimal("-10.00"),
    )
    db.add(invalid_test)

    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_booking_status_defaults_to_pending(db):
    user = User(
        email=f"patient_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="mock_hashed_password",
        full_name="John Doe",
    )
    centre = DiagnosticCentre(
        name=f"Booking Centre {uuid.uuid4().hex[:6]}",
        location="Whitefield, Bangalore",
        contact_number="+919876543203",
    )
    db.add_all([user, centre])
    db.flush()

    test = DiagnosticTest(
        centre_id=centre.id,
        name="Blood Glucose",
        price=Decimal("150.00"),
    )
    db.add(test)
    db.flush()

    booking = Booking(
        user_id=user.id,
        centre_id=centre.id,
        test_id=test.id,
        appointment_datetime=datetime.now(timezone.utc),
        amount=test.price,  # Snapshot
    )
    db.add(booking)
    db.flush()

    assert booking.status == BookingStatus.PENDING
    assert booking.amount == Decimal("150.00")
    assert booking.user.id == user.id
    assert booking.centre.id == centre.id
    assert booking.test.id == test.id


def test_payment_status_and_transaction_ref_uniqueness(db):
    user = User(
        email=f"patient_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="mock_hashed_password",
        full_name="Jane Doe",
    )
    centre = DiagnosticCentre(
        name=f"Payment Centre {uuid.uuid4().hex[:6]}",
        location="HSR Layout, Bangalore",
        contact_number="+919876543204",
    )
    db.add_all([user, centre])
    db.flush()

    test = DiagnosticTest(
        centre_id=centre.id,
        name="ECG",
        price=Decimal("350.00"),
    )
    db.add(test)
    db.flush()

    booking = Booking(
        user_id=user.id,
        centre_id=centre.id,
        test_id=test.id,
        appointment_datetime=datetime.now(timezone.utc),
        amount=test.price,
    )
    db.add(booking)
    db.flush()

    txn_ref = f"TXN_{uuid.uuid4().hex[:8].upper()}"
    payment = Payment(
        booking_id=booking.id,
        transaction_reference=txn_ref,
        amount=booking.amount,
        status=PaymentStatus.SUCCESS,
    )
    db.add(payment)
    db.flush()

    assert payment.status == PaymentStatus.SUCCESS
    assert payment.payment_method == "SIMULATED"

    # Duplicate transaction_reference should fail
    duplicate_payment = Payment(
        booking_id=booking.id,
        transaction_reference=txn_ref,
        amount=booking.amount,
        status=PaymentStatus.FAILED,
    )
    db.add(duplicate_payment)

    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_webhook_event_id_uniqueness_and_jsonb_payload(db):
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    payload_data = {
        "provider": "mock_gateway",
        "nested": {"status": "SUCCESS", "code": 200},
        "meta": ["item1", "item2"],
    }

    event = WebhookEvent(
        event_id=event_id,
        event_type="payment.success",
        payload=payload_data,
    )
    db.add(event)
    db.flush()

    # Verify JSONB retrieval
    retrieved = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
    assert retrieved is not None
    assert retrieved.payload["provider"] == "mock_gateway"
    assert retrieved.payload["nested"]["status"] == "SUCCESS"

    # Duplicate event_id must fail
    duplicate_event = WebhookEvent(
        event_id=event_id,
        event_type="payment.success",
        payload={"duplicate": True},
    )
    db.add(duplicate_event)

    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_foreign_key_delete_restrict_on_centre(db):
    centre = DiagnosticCentre(
        name=f"Restrict Centre {uuid.uuid4().hex[:6]}",
        location="MG Road, Bangalore",
        contact_number="+919876543205",
    )
    db.add(centre)
    db.flush()

    test = DiagnosticTest(
        centre_id=centre.id,
        name="Calcium Test",
        price=Decimal("400.00"),
    )
    db.add(test)
    db.flush()

    # Attempting to delete centre when it has active tests must raise IntegrityError (RESTRICT)
    db.delete(centre)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
