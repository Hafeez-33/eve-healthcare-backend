import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.booking import Booking
from app.models.diagnostic_test import DiagnosticTest
from app.models.enums import BookingStatus, PaymentStatus
from app.models.payment import Payment

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

def create_user(client: TestClient, label: str = "user") -> tuple[str, dict]:
    """Helper to create a user and return (user_id, auth_headers)."""
    email = f"{label}_{uuid.uuid4().hex[:8]}@example.com"
    signup_res = client.post(
        "/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": f"Payment User {label}"},
    )
    user_id = signup_res.json()["id"]
    token = create_access_token(subject=user_id)
    headers = {"Authorization": f"Bearer {token}"}
    return user_id, headers


@pytest.fixture
def user_a():
    return create_user(client, label="user_a")


@pytest.fixture
def user_b():
    return create_user(client, label="user_b")


@pytest.fixture
def pending_booking(user_a):
    """Creates a sample diagnostic centre, test, and pending booking for User A."""
    _, headers = user_a

    # Create centre
    centre_res = client.post(
        "/centres/",
        json={
            "name": f"Payment Lab {uuid.uuid4().hex[:6]}",
            "location": "Indiranagar, Bangalore",
            "contact_number": "+918025531999",
        },
        headers=headers,
    )
    centre_id = centre_res.json()["id"]

    # Create test at ₹450.00
    test_res = client.post(
        f"/centres/{centre_id}/tests",
        json={
            "name": f"CBC Test {uuid.uuid4().hex[:6]}",
            "description": "Standard CBC test",
            "price": "450.00",
        },
        headers=headers,
    )
    test_id = test_res.json()["id"]

    # Create booking for User A
    booking_res = client.post(
        "/bookings/",
        json={
            "centre_id": centre_id,
            "test_id": test_id,
            "appointment_datetime": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        },
        headers=headers,
    )
    booking_data = booking_res.json()
    return {
        "centre_id": centre_id,
        "test_id": test_id,
        "booking_id": booking_data["id"],
        "amount": Decimal(str(booking_data["amount"])),
    }


# ---------------------------------------------------------------------------
# 1. Authentication Tests
# ---------------------------------------------------------------------------

def test_unauthenticated_payment_creation_returns_401(pending_booking):
    payload = {
        "booking_id": pending_booking["booking_id"],
        "simulate_status": "SUCCESS",
    }
    response = client.post("/payments/", json=payload)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 2. Payment Creation & Booking Transitions
# ---------------------------------------------------------------------------

def test_simulated_payment_success_confirms_booking(user_a, pending_booking):
    _, headers = user_a
    booking_id = pending_booking["booking_id"]

    payload = {
        "booking_id": booking_id,
        "simulate_status": "SUCCESS",
    }
    response = client.post("/payments/", json=payload, headers=headers)
    assert response.status_code == 201

    payment_data = response.json()
    assert payment_data["booking_id"] == booking_id
    assert payment_data["status"] == "SUCCESS"
    assert payment_data["payment_method"] == "SIMULATED"
    assert Decimal(str(payment_data["amount"])) == pending_booking["amount"]
    assert payment_data["transaction_reference"].startswith("TXN_SIM_")

    # Verify booking status transitioned from PENDING to CONFIRMED
    booking_res = client.get(f"/bookings/{booking_id}", headers=headers)
    assert booking_res.status_code == 200
    assert booking_res.json()["status"] == "CONFIRMED"


def test_simulated_payment_failure_fails_booking(user_a, pending_booking):
    _, headers = user_a
    booking_id = pending_booking["booking_id"]

    payload = {
        "booking_id": booking_id,
        "simulate_status": "FAILED",
    }
    response = client.post("/payments/", json=payload, headers=headers)
    assert response.status_code == 201

    payment_data = response.json()
    assert payment_data["booking_id"] == booking_id
    assert payment_data["status"] == "FAILED"

    # Verify booking status transitioned from PENDING to FAILED
    booking_res = client.get(f"/bookings/{booking_id}", headers=headers)
    assert booking_res.status_code == 200
    assert booking_res.json()["status"] == "FAILED"


def test_payment_amount_invariant_after_catalogue_test_price_change(user_a, pending_booking):
    """Payment amount MUST come from booking.amount snapshot, never diagnostic_tests.price."""
    _, headers = user_a
    booking_id = pending_booking["booking_id"]
    test_id = pending_booking["test_id"]
    original_booking_amount = pending_booking["amount"]  # 450.00

    # Modify the diagnostic test price in the database from 450.00 to 999.00
    with SessionLocal() as db:
        test = db.get(DiagnosticTest, uuid.UUID(test_id))
        test.price = Decimal("999.00")
        db.commit()

    # Initiate payment
    payload = {
        "booking_id": booking_id,
        "simulate_status": "SUCCESS",
    }
    response = client.post("/payments/", json=payload, headers=headers)
    assert response.status_code == 201

    # Payment amount must strictly be ₹450.00 (booking snapshot), NOT ₹999.00
    assert Decimal(str(response.json()["amount"])) == original_booking_amount


def test_payment_has_unique_transaction_reference(user_a, pending_booking):
    _, headers = user_a
    booking_id = pending_booking["booking_id"]

    payload = {
        "booking_id": booking_id,
        "simulate_status": "SUCCESS",
    }
    response = client.post("/payments/", json=payload, headers=headers)
    assert response.status_code == 201
    txn_ref = response.json()["transaction_reference"]

    # Verify uniqueness in database
    with SessionLocal() as db:
        payments = db.query(Payment).filter(Payment.transaction_reference == txn_ref).all()
        assert len(payments) == 1


def test_payment_for_nonexistent_booking_returns_404(user_a):
    _, headers = user_a
    payload = {
        "booking_id": str(uuid.uuid4()),
        "simulate_status": "SUCCESS",
    }
    response = client.post("/payments/", json=payload, headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


def test_cross_user_payment_returns_403(user_b, pending_booking):
    """User B cannot initiate payment for User A's booking."""
    _, headers_b = user_b
    payload = {
        "booking_id": pending_booking["booking_id"],
        "simulate_status": "SUCCESS",
    }
    response = client.post("/payments/", json=payload, headers=headers_b)
    assert response.status_code == 403
    assert response.json()["detail"] == "Access to this booking is forbidden"


# ---------------------------------------------------------------------------
# 3. Terminal State Checks
# ---------------------------------------------------------------------------

def test_payment_on_confirmed_booking_returns_409(user_a, pending_booking):
    _, headers = user_a
    booking_id = pending_booking["booking_id"]

    # First payment succeeds -> booking becomes CONFIRMED
    res1 = client.post(
        "/payments/",
        json={"booking_id": booking_id, "simulate_status": "SUCCESS"},
        headers=headers,
    )
    assert res1.status_code == 201

    # Second payment attempt must be rejected with 409 Conflict
    res2 = client.post(
        "/payments/",
        json={"booking_id": booking_id, "simulate_status": "SUCCESS"},
        headers=headers,
    )
    assert res2.status_code == 409
    assert "Cannot pay for booking with status CONFIRMED" in res2.json()["detail"]


def test_payment_on_failed_booking_returns_409(user_a, pending_booking):
    _, headers = user_a
    booking_id = pending_booking["booking_id"]

    # Payment fails -> booking becomes FAILED
    res1 = client.post(
        "/payments/",
        json={"booking_id": booking_id, "simulate_status": "FAILED"},
        headers=headers,
    )
    assert res1.status_code == 201

    # Second payment attempt must be rejected with 409 Conflict
    res2 = client.post(
        "/payments/",
        json={"booking_id": booking_id, "simulate_status": "SUCCESS"},
        headers=headers,
    )
    assert res2.status_code == 409
    assert "Cannot pay for booking with status FAILED" in res2.json()["detail"]


def test_payment_on_cancelled_booking_returns_409(user_a, pending_booking):
    _, headers = user_a
    booking_id = pending_booking["booking_id"]

    # Cancel booking -> CANCELLED
    cancel_res = client.patch(f"/bookings/{booking_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Payment attempt must be rejected with 409 Conflict
    pay_res = client.post(
        "/payments/",
        json={"booking_id": booking_id, "simulate_status": "SUCCESS"},
        headers=headers,
    )
    assert pay_res.status_code == 409
    assert "Cannot pay for booking with status CANCELLED" in pay_res.json()["detail"]


def test_payment_response_does_not_leak_internals(user_a, pending_booking):
    _, headers = user_a
    res = client.post(
        "/payments/",
        json={"booking_id": pending_booking["booking_id"], "simulate_status": "SUCCESS"},
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    internal_keys = {"_sa_instance_state", "password", "metadata"}
    assert internal_keys.isdisjoint(data.keys())


def test_payment_txn_reference_uniqueness_db_constraint(pending_booking):
    """Direct database insertion of duplicate transaction_reference raises IntegrityError."""
    booking_id = uuid.UUID(pending_booking["booking_id"])
    dup_ref = f"TXN_DUP_{uuid.uuid4().hex[:8].upper()}"

    with SessionLocal() as db:
        p1 = Payment(
            booking_id=booking_id,
            transaction_reference=dup_ref,
            amount=Decimal("450.00"),
            status=PaymentStatus.SUCCESS,
        )
        db.add(p1)
        db.commit()

        p2 = Payment(
            booking_id=booking_id,
            transaction_reference=dup_ref,
            amount=Decimal("450.00"),
            status=PaymentStatus.SUCCESS,
        )
        db.add(p2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
