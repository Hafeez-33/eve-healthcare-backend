import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.booking import Booking
from app.models.diagnostic_centre import DiagnosticCentre
from app.models.enums import BookingStatus
from app.models.webhook_event import WebhookEvent
from app.services.booking_service import transition_booking_status

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_user():
    email = f"hardening_{uuid.uuid4().hex[:8]}@example.com"
    signup_res = client.post(
        "/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": "Hardening User"},
    )
    user_id = signup_res.json()["id"]
    token = create_access_token(subject=user_id)
    return {"user_id": user_id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def sample_centre_and_test(auth_user):
    headers = auth_user["headers"]
    centre_res = client.post(
        "/centres/",
        json={
            "name": f"Hardening Centre {uuid.uuid4().hex[:6]}",
            "location": "Whitefield, Bangalore",
            "contact_number": "+918025539999",
        },
        headers=headers,
    )
    centre_id = centre_res.json()["id"]

    test_res = client.post(
        f"/centres/{centre_id}/tests",
        json={
            "name": f"Hardening Test {uuid.uuid4().hex[:6]}",
            "description": "Comprehensive panel",
            "price": "600.00",
        },
        headers=headers,
    )
    test_id = test_res.json()["id"]
    return {"centre_id": centre_id, "test_id": test_id, "price": Decimal("600.00")}


# ---------------------------------------------------------------------------
# 1. Authentication & JWT Hardening
# ---------------------------------------------------------------------------

def test_invalid_bearer_token_string_rejected():
    headers = {"Authorization": "Bearer not-a-valid-token-at-all"}
    res_centre = client.post("/centres/", json={"name": "X", "location": "Y", "contact_number": "123"}, headers=headers)
    assert res_centre.status_code == 401

    res_booking = client.post("/bookings/", json={"centre_id": str(uuid.uuid4()), "test_id": str(uuid.uuid4()), "appointment_datetime": "2026-12-01T10:00:00Z"}, headers=headers)
    assert res_booking.status_code == 401

    res_payment = client.post("/payments/", json={"booking_id": str(uuid.uuid4())}, headers=headers)
    assert res_payment.status_code == 401


def test_malformed_authorization_scheme_rejected():
    headers = {"Authorization": "Basic dXNlcjpwYXNz"}
    response = client.get("/bookings/", headers=headers)
    assert response.status_code == 401


def test_jwt_with_nonexistent_user_id_rejected():
    random_user_id = str(uuid.uuid4())
    token = create_access_token(subject=random_user_id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/bookings/", headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "User not found"


# ---------------------------------------------------------------------------
# 2. Ownership & IDOR Data Leakage Protection
# ---------------------------------------------------------------------------

def test_forbidden_booking_error_leaks_zero_resource_data(auth_user, sample_centre_and_test):
    user_a = auth_user

    # User B
    email_b = f"user_b_{uuid.uuid4().hex[:8]}@example.com"
    res_b = client.post("/auth/signup", json={"email": email_b, "password": "Password123!", "full_name": "User B"})
    token_b = create_access_token(subject=res_b.json()["id"])
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A creates a booking
    res_booking = client.post(
        "/bookings/",
        json={
            "centre_id": sample_centre_and_test["centre_id"],
            "test_id": sample_centre_and_test["test_id"],
            "appointment_datetime": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        },
        headers=user_a["headers"],
    )
    booking_id = res_booking.json()["id"]

    # User B attempts to access User A's booking
    res_access = client.get(f"/bookings/{booking_id}", headers=headers_b)
    assert res_access.status_code == 403
    # Check that error body strictly contains only the error message and leaks no user or booking details
    data = res_access.json()
    assert data == {"detail": "Access to this booking is forbidden"}
    assert "amount" not in data
    assert "user_id" not in data
    assert "test_id" not in data


# ---------------------------------------------------------------------------
# 3. Catalogue Validation & Edge Cases
# ---------------------------------------------------------------------------

def test_create_test_excessive_decimal_places_rejected(auth_user, sample_centre_and_test):
    headers = auth_user["headers"]
    centre_id = sample_centre_and_test["centre_id"]

    # 3 decimal places violates decimal_places=2
    response = client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "Precision Test", "price": "199.999"},
        headers=headers,
    )
    assert response.status_code == 422


def test_create_centre_oversized_contact_number_rejected(auth_user):
    headers = auth_user["headers"]
    response = client.post(
        "/centres/",
        json={
            "name": "Invalid Centre",
            "location": "MG Road",
            "contact_number": "+918025531234567890123456789",  # > 25 characters
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_centres_pagination_boundaries():
    # limit = 0 violates ge=1
    res1 = client.get("/centres/?limit=0")
    assert res1.status_code == 422

    # limit = 101 violates le=100
    res2 = client.get("/centres/?limit=101")
    assert res2.status_code == 422

    # skip = -1 violates ge=0
    res3 = client.get("/centres/?skip=-1")
    assert res3.status_code == 422


def test_get_centre_tests_malformed_uuid():
    response = client.get("/centres/not-a-valid-uuid/tests")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 4. Booking Timezone & Pagination Hardening
# ---------------------------------------------------------------------------

def test_booking_appointment_datetime_timezone_offset_preserved(auth_user, sample_centre_and_test):
    headers = auth_user["headers"]
    # Provide explicit IST offset (+05:30)
    future_ist = (datetime.now(timezone.utc) + timedelta(days=5)).astimezone(
        timezone(timedelta(hours=5, minutes=30))
    ).isoformat()

    response = client.post(
        "/bookings/",
        json={
            "centre_id": sample_centre_and_test["centre_id"],
            "test_id": sample_centre_and_test["test_id"],
            "appointment_datetime": future_ist,
        },
        headers=headers,
    )
    assert response.status_code == 201
    created_dt = response.json()["appointment_datetime"]
    assert created_dt is not None


def test_bookings_pagination_boundaries(auth_user):
    headers = auth_user["headers"]

    res1 = client.get("/bookings/?limit=0", headers=headers)
    assert res1.status_code == 422

    res2 = client.get("/bookings/?limit=101", headers=headers)
    assert res2.status_code == 422

    res3 = client.get("/bookings/?skip=-1", headers=headers)
    assert res3.status_code == 422


# ---------------------------------------------------------------------------
# 5. State Machine Invariant Exhaustive Tests
# ---------------------------------------------------------------------------

def test_state_machine_terminal_to_self_transitions_rejected(auth_user, sample_centre_and_test):
    user_id = auth_user["user_id"]
    centre_id = sample_centre_and_test["centre_id"]
    test_id = sample_centre_and_test["test_id"]

    with SessionLocal() as db:
        booking = Booking(
            user_id=uuid.UUID(user_id),
            centre_id=uuid.UUID(centre_id),
            test_id=uuid.UUID(test_id),
            appointment_datetime=datetime.now(timezone.utc) + timedelta(days=1),
            amount=Decimal("600.00"),
            status=BookingStatus.PENDING,
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

        # PENDING -> PENDING must be rejected
        with pytest.raises(HTTPException) as exc:
            transition_booking_status(db, booking, BookingStatus.PENDING)
        assert exc.value.status_code == 409

        # Move to CONFIRMED
        transition_booking_status(db, booking, BookingStatus.CONFIRMED)
        assert booking.status == BookingStatus.CONFIRMED

        # CONFIRMED -> CONFIRMED must be rejected
        with pytest.raises(HTTPException) as exc:
            transition_booking_status(db, booking, BookingStatus.CONFIRMED)
        assert exc.value.status_code == 409


def test_state_machine_failed_to_self_rejected(auth_user, sample_centre_and_test):
    user_id = auth_user["user_id"]
    centre_id = sample_centre_and_test["centre_id"]
    test_id = sample_centre_and_test["test_id"]

    with SessionLocal() as db:
        booking = Booking(
            user_id=uuid.UUID(user_id),
            centre_id=uuid.UUID(centre_id),
            test_id=uuid.UUID(test_id),
            appointment_datetime=datetime.now(timezone.utc) + timedelta(days=1),
            amount=Decimal("600.00"),
            status=BookingStatus.PENDING,
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

        transition_booking_status(db, booking, BookingStatus.FAILED)
        assert booking.status == BookingStatus.FAILED

        # FAILED -> FAILED must be rejected
        with pytest.raises(HTTPException) as exc:
            transition_booking_status(db, booking, BookingStatus.FAILED)
        assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# 6. Payment & Webhook Validation Hardening
# ---------------------------------------------------------------------------

def test_payment_invalid_simulate_status_rejected(auth_user):
    headers = auth_user["headers"]
    response = client.post(
        "/payments/",
        json={"booking_id": str(uuid.uuid4()), "simulate_status": "PENDING"},
        headers=headers,
    )
    # PaymentStatus only allows SUCCESS or FAILED
    assert response.status_code == 422


def test_webhook_zero_and_negative_amount_rejected():
    res_zero = client.post(
        "/payments/webhook/",
        json={
            "event_id": f"evt_{uuid.uuid4().hex[:8]}",
            "event_type": "payment.updated",
            "data": {
                "transaction_reference": "TXN_123",
                "booking_id": str(uuid.uuid4()),
                "amount": "0.00",
                "status": "SUCCESS",
            },
        },
    )
    assert res_zero.status_code == 422

    res_neg = client.post(
        "/payments/webhook/",
        json={
            "event_id": f"evt_{uuid.uuid4().hex[:8]}",
            "event_type": "payment.updated",
            "data": {
                "transaction_reference": "TXN_123",
                "booking_id": str(uuid.uuid4()),
                "amount": "-50.00",
                "status": "SUCCESS",
            },
        },
    )
    assert res_neg.status_code == 422


def test_webhook_invalid_status_enum_rejected():
    response = client.post(
        "/payments/webhook/",
        json={
            "event_id": f"evt_{uuid.uuid4().hex[:8]}",
            "event_type": "payment.updated",
            "data": {
                "transaction_reference": "TXN_123",
                "booking_id": str(uuid.uuid4()),
                "amount": "450.00",
                "status": "PENDING",  # Invalid in WebhookPaymentData
            },
        },
    )
    assert response.status_code == 422


def test_webhook_empty_event_id_rejected():
    response = client.post(
        "/payments/webhook/",
        json={
            "event_id": "",
            "event_type": "payment.updated",
            "data": {
                "transaction_reference": "TXN_123",
                "booking_id": str(uuid.uuid4()),
                "amount": "450.00",
                "status": "SUCCESS",
            },
        },
    )
    assert response.status_code == 422


def test_webhook_nonexistent_booking_leaves_no_orphaned_event():
    event_id = f"evt_orphan_{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/payments/webhook/",
        json={
            "event_id": event_id,
            "event_type": "payment.updated",
            "data": {
                "transaction_reference": "TXN_ORPHAN",
                "booking_id": str(uuid.uuid4()),
                "amount": "450.00",
                "status": "SUCCESS",
            },
        },
    )
    assert response.status_code == 404

    # Verify no row was inserted into webhook_events
    with SessionLocal() as db:
        event = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
        assert event is None


# ---------------------------------------------------------------------------
# 7. Session Resilience After Handled IntegrityError
# ---------------------------------------------------------------------------

def test_session_resilience_after_integrity_error():
    """Confirms that catching and rolling back an IntegrityError leaves the SQLAlchemy session clean."""
    with SessionLocal() as db:
        # Create centre
        c1 = DiagnosticCentre(
            name=f"Resilience Centre {uuid.uuid4().hex[:6]}",
            location="Koramangala",
            contact_number="+918025531234",
        )
        db.add(c1)
        db.commit()

        # Intentionally cause duplicate key error on User email
        from app.models.user import User
        unique_email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
        u1 = User(email=unique_email, hashed_password="pw", full_name="User 1")
        u2 = User(email=unique_email, hashed_password="pw", full_name="User 2")
        db.add(u1)
        db.commit()

        db.add(u2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # Session must remain fully functional for subsequent queries
        queried_centre = db.get(DiagnosticCentre, c1.id)
        assert queried_centre is not None
        assert queried_centre.name == c1.name


# ---------------------------------------------------------------------------
# 8. Sensitive Data Exposure Audit
# ---------------------------------------------------------------------------

def test_api_responses_do_not_expose_passwords_or_hashes(auth_user):
    headers = auth_user["headers"]

    # Signup & Login responses
    signup_res = client.post(
        "/auth/signup",
        json={"email": f"audit_{uuid.uuid4().hex[:8]}@example.com", "password": "Password123!", "full_name": "Audit User"},
    )
    assert "password" not in signup_res.json()
    assert "hashed_password" not in signup_res.json()

    # Centres list & detail
    centres_res = client.get("/centres/")
    assert isinstance(centres_res.json(), list)
    for c in centres_res.json():
        assert "password" not in c
        assert "_sa_instance_state" not in c

    # Bookings list
    bookings_res = client.get("/bookings/", headers=headers)
    assert isinstance(bookings_res.json(), list)
    for b in bookings_res.json():
        assert "password" not in b
        assert "_sa_instance_state" not in b
