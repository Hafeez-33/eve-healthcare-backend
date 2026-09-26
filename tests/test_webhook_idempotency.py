import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.booking import Booking
from app.models.enums import BookingStatus, PaymentStatus
from app.models.payment import Payment
from app.models.webhook_event import WebhookEvent

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def test_setup():
    """Sets up a user, centre, test, and pending booking."""
    email = f"wh_user_{uuid.uuid4().hex[:8]}@example.com"
    signup_res = client.post(
        "/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Webhook Test User"},
    )
    user_id = signup_res.json()["id"]
    token = create_access_token(subject=user_id)
    headers = {"Authorization": f"Bearer {token}"}

    # Create centre
    centre_res = client.post(
        "/centres/",
        json={
            "name": f"Webhook Diagnostic Centre {uuid.uuid4().hex[:6]}",
            "location": "Koramangala, Bangalore",
            "contact_number": "+918025538888",
        },
        headers=headers,
    )
    centre_id = centre_res.json()["id"]

    # Create test at ₹500.00
    test_res = client.post(
        f"/centres/{centre_id}/tests",
        json={
            "name": f"Thyroid Profile {uuid.uuid4().hex[:6]}",
            "description": "T3, T4, TSH",
            "price": "500.00",
        },
        headers=headers,
    )
    test_id = test_res.json()["id"]

    # Create booking
    booking_res = client.post(
        "/bookings/",
        json={
            "centre_id": centre_id,
            "test_id": test_id,
            "appointment_datetime": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        },
        headers=headers,
    )
    booking_data = booking_res.json()

    return {
        "headers": headers,
        "booking_id": booking_data["id"],
        "amount": Decimal(str(booking_data["amount"])),
    }


def make_webhook_payload(booking_id: str, amount: str = "500.00", status: str = "SUCCESS") -> dict:
    return {
        "event_id": f"evt_test_{uuid.uuid4().hex[:12]}",
        "event_type": "payment.updated",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "transaction_reference": f"TXN_PG_{uuid.uuid4().hex[:8].upper()}",
            "booking_id": booking_id,
            "amount": amount,
            "status": status,
        },
    }


# ---------------------------------------------------------------------------
# 1. Basic Webhook Behavior
# ---------------------------------------------------------------------------

def test_webhook_success_confirms_pending_booking(test_setup):
    booking_id = test_setup["booking_id"]
    payload = make_webhook_payload(booking_id, amount="500.00", status="SUCCESS")

    response = client.post("/payments/webhook/", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "processed"
    assert data["event_id"] == payload["event_id"]
    assert data["booking_status"] == "CONFIRMED"

    # Verify database state
    with SessionLocal() as db:
        booking = db.get(Booking, uuid.UUID(booking_id))
        assert booking.status == BookingStatus.CONFIRMED

        payment = (
            db.query(Payment)
            .filter(Payment.transaction_reference == payload["data"]["transaction_reference"])
            .first()
        )
        assert payment is not None
        assert payment.amount == Decimal("500.00")
        assert payment.status == PaymentStatus.SUCCESS

        event = (
            db.query(WebhookEvent)
            .filter(WebhookEvent.event_id == payload["event_id"])
            .first()
        )
        assert event is not None
        assert event.processed_at is not None


def test_webhook_failure_fails_pending_booking(test_setup):
    booking_id = test_setup["booking_id"]
    payload = make_webhook_payload(booking_id, amount="500.00", status="FAILED")

    response = client.post("/payments/webhook/", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "processed"
    assert data["booking_status"] == "FAILED"

    with SessionLocal() as db:
        booking = db.get(Booking, uuid.UUID(booking_id))
        assert booking.status == BookingStatus.FAILED


def test_webhook_unknown_booking_returns_404():
    payload = make_webhook_payload(str(uuid.uuid4()), amount="500.00", status="SUCCESS")
    response = client.post("/payments/webhook/", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


def test_webhook_malformed_payload_returns_422():
    # Missing required fields
    response = client.post("/payments/webhook/", json={"invalid": "payload"})
    assert response.status_code == 422


def test_webhook_amount_mismatch_returns_400_and_keeps_pending(test_setup):
    booking_id = test_setup["booking_id"]
    # Booking amount is ₹500.00, but webhook asserts ₹250.00
    payload = make_webhook_payload(booking_id, amount="250.00", status="SUCCESS")

    response = client.post("/payments/webhook/", json=payload)
    assert response.status_code == 400
    assert "AMOUNT_MISMATCH" in response.json()["detail"]

    # Transaction was rolled back: booking remains PENDING and no payment created
    with SessionLocal() as db:
        booking = db.get(Booking, uuid.UUID(booking_id))
        assert booking.status == BookingStatus.PENDING

        payment = (
            db.query(Payment)
            .filter(Payment.transaction_reference == payload["data"]["transaction_reference"])
            .first()
        )
        assert payment is None


# ---------------------------------------------------------------------------
# 2. Webhook Idempotency (Sequential Duplicate Delivery)
# ---------------------------------------------------------------------------

def test_webhook_idempotency_duplicate_event_returns_200_already_processed(test_setup):
    booking_id = test_setup["booking_id"]
    payload = make_webhook_payload(booking_id, amount="500.00", status="SUCCESS")

    # 1. First webhook delivery -> processed
    res1 = client.post("/payments/webhook/", json=payload)
    assert res1.status_code == 200
    assert res1.json()["status"] == "processed"

    # 2. Second webhook delivery with identical event_id -> already_processed
    res2 = client.post("/payments/webhook/", json=payload)
    assert res2.status_code == 200
    assert res2.json()["status"] == "already_processed"
    assert res2.json()["event_id"] == payload["event_id"]

    # 3. Third delivery with identical event_id -> already_processed
    res3 = client.post("/payments/webhook/", json=payload)
    assert res3.status_code == 200
    assert res3.json()["status"] == "already_processed"

    # Verify database: exactly 1 webhook_events row, exactly 1 payment record
    with SessionLocal() as db:
        events = (
            db.query(WebhookEvent)
            .filter(WebhookEvent.event_id == payload["event_id"])
            .all()
        )
        assert len(events) == 1

        payments = (
            db.query(Payment)
            .filter(Payment.booking_id == uuid.UUID(booking_id))
            .all()
        )
        assert len(payments) == 1


# ---------------------------------------------------------------------------
# 3. Terminal State Invariant Guards
# ---------------------------------------------------------------------------

def test_failure_webhook_on_confirmed_booking_does_not_become_failed(test_setup):
    booking_id = test_setup["booking_id"]

    # First confirm booking via successful webhook
    payload1 = make_webhook_payload(booking_id, amount="500.00", status="SUCCESS")
    client.post("/payments/webhook/", json=payload1)

    # Subsequent failure webhook with new event_id must not alter CONFIRMED status
    payload2 = make_webhook_payload(booking_id, amount="500.00", status="FAILED")
    res2 = client.post("/payments/webhook/", json=payload2)
    assert res2.status_code == 200

    with SessionLocal() as db:
        booking = db.get(Booking, uuid.UUID(booking_id))
        assert booking.status == BookingStatus.CONFIRMED


def test_success_webhook_on_failed_booking_does_not_become_confirmed(test_setup):
    booking_id = test_setup["booking_id"]

    # First fail booking
    payload1 = make_webhook_payload(booking_id, amount="500.00", status="FAILED")
    client.post("/payments/webhook/", json=payload1)

    # Subsequent success webhook must not resurrect FAILED booking
    payload2 = make_webhook_payload(booking_id, amount="500.00", status="SUCCESS")
    res2 = client.post("/payments/webhook/", json=payload2)
    assert res2.status_code == 200

    with SessionLocal() as db:
        booking = db.get(Booking, uuid.UUID(booking_id))
        assert booking.status == BookingStatus.FAILED


def test_success_webhook_on_cancelled_booking_does_not_become_confirmed(test_setup):
    headers = test_setup["headers"]
    booking_id = test_setup["booking_id"]

    # User cancels booking
    cancel_res = client.patch(f"/bookings/{booking_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Webhook arrives reporting SUCCESS -> booking must stay CANCELLED
    payload = make_webhook_payload(booking_id, amount="500.00", status="SUCCESS")
    res = client.post("/payments/webhook/", json=payload)
    assert res.status_code == 200

    with SessionLocal() as db:
        booking = db.get(Booking, uuid.UUID(booking_id))
        assert booking.status == BookingStatus.CANCELLED


def test_failure_webhook_on_cancelled_booking_does_not_become_failed(test_setup):
    headers = test_setup["headers"]
    booking_id = test_setup["booking_id"]

    # User cancels booking
    client.patch(f"/bookings/{booking_id}/cancel", headers=headers)

    # Webhook arrives reporting FAILED -> booking must stay CANCELLED
    payload = make_webhook_payload(booking_id, amount="500.00", status="FAILED")
    res = client.post("/payments/webhook/", json=payload)
    assert res.status_code == 200

    with SessionLocal() as db:
        booking = db.get(Booking, uuid.UUID(booking_id))
        assert booking.status == BookingStatus.CANCELLED


# ---------------------------------------------------------------------------
# 4. Concurrency Test — Atomic Idempotency Under Parallel Load
# ---------------------------------------------------------------------------

def test_webhook_concurrent_duplicates(test_setup):
    """5 concurrent identical webhook requests execute safely against PostgreSQL.
    
    Exactly 1 request returns 'processed', 4 return 'already_processed'.
    Exactly 1 webhook_events row is inserted.
    Exactly 1 payment record is created.
    Final booking status is CONFIRMED.
    """
    booking_id = test_setup["booking_id"]
    identical_payload = make_webhook_payload(booking_id, amount="500.00", status="SUCCESS")

    def send_webhook():
        # Each thread uses a fresh client request against local PostgreSQL
        return client.post("/payments/webhook/", json=identical_payload)

    # Fire 5 concurrent requests using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(send_webhook) for _ in range(5)]
        responses = [f.result() for f in futures]

    # Verify all responses succeeded with HTTP 200 OK
    assert all(r.status_code == 200 for r in responses)

    statuses = [r.json()["status"] for r in responses]
    assert statuses.count("processed") == 1
    assert statuses.count("already_processed") == 4

    # Verify PostgreSQL database state
    with SessionLocal() as db:
        # Exactly one webhook_events record with this event_id
        events = (
            db.query(WebhookEvent)
            .filter(WebhookEvent.event_id == identical_payload["event_id"])
            .all()
        )
        assert len(events) == 1

        # Exactly one payment record for this transaction reference
        payments = (
            db.query(Payment)
            .filter(Payment.transaction_reference == identical_payload["data"]["transaction_reference"])
            .all()
        )
        assert len(payments) == 1

        # Final booking status is CONFIRMED
        booking = db.get(Booking, uuid.UUID(booking_id))
        assert booking.status == BookingStatus.CONFIRMED
