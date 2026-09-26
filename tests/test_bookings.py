import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.booking import Booking
from app.models.diagnostic_test import DiagnosticTest
from app.models.enums import BookingStatus
from app.services.booking_service import transition_booking_status

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

def create_test_user(client: TestClient, label: str = "user") -> tuple[str, dict]:
    """Helper to create a user and return (user_id, auth_headers)."""
    email = f"{label}_{uuid.uuid4().hex[:8]}@example.com"
    signup_res = client.post(
        "/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": f"Test {label}"},
    )
    user_id = signup_res.json()["id"]
    token = create_access_token(subject=user_id)
    headers = {"Authorization": f"Bearer {token}"}
    return user_id, headers


@pytest.fixture
def user_a():
    return create_test_user(client, label="user_a")


@pytest.fixture
def user_b():
    return create_test_user(client, label="user_b")


@pytest.fixture
def catalogue(user_a):
    """Creates a sample diagnostic centre and diagnostic test."""
    _, headers = user_a

    # Create centre
    centre_res = client.post(
        "/centres/",
        json={
            "name": f"Apollo Centre {uuid.uuid4().hex[:6]}",
            "location": "Indiranagar, Bangalore",
            "contact_number": "+918025531000",
        },
        headers=headers,
    )
    centre_id = centre_res.json()["id"]

    # Create test under centre
    test_res = client.post(
        f"/centres/{centre_id}/tests",
        json={
            "name": f"Complete Blood Count {uuid.uuid4().hex[:6]}",
            "description": "Standard CBC test",
            "price": "450.00",
        },
        headers=headers,
    )
    test_id = test_res.json()["id"]

    return {"centre_id": centre_id, "test_id": test_id, "price": Decimal("450.00")}


def get_future_datetime(hours: int = 48) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


# ---------------------------------------------------------------------------
# 1. Authentication Tests
# ---------------------------------------------------------------------------

def test_create_booking_unauthenticated_returns_401(catalogue):
    payload = {
        "centre_id": catalogue["centre_id"],
        "test_id": catalogue["test_id"],
        "appointment_datetime": get_future_datetime(),
    }
    response = client.post("/bookings/", json=payload)
    assert response.status_code == 401


def test_list_bookings_unauthenticated_returns_401():
    response = client.get("/bookings/")
    assert response.status_code == 401


def test_get_booking_unauthenticated_returns_401():
    random_id = uuid.uuid4()
    response = client.get(f"/bookings/{random_id}")
    assert response.status_code == 401


def test_cancel_booking_unauthenticated_returns_401():
    random_id = uuid.uuid4()
    response = client.patch(f"/bookings/{random_id}/cancel")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 2. Booking Creation & Validation Tests
# ---------------------------------------------------------------------------

def test_create_booking_success_defaults_to_pending(user_a, catalogue):
    user_id, headers = user_a
    appointment_dt = get_future_datetime(24)

    payload = {
        "centre_id": catalogue["centre_id"],
        "test_id": catalogue["test_id"],
        "appointment_datetime": appointment_dt,
    }
    response = client.post("/bookings/", json=payload, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["centre_id"] == catalogue["centre_id"]
    assert data["test_id"] == catalogue["test_id"]
    assert data["user_id"] == user_id
    assert data["status"] == "PENDING"
    assert Decimal(str(data["amount"])) == catalogue["price"]
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_booking_nonexistent_centre_returns_404(user_a, catalogue):
    _, headers = user_a
    payload = {
        "centre_id": str(uuid.uuid4()),
        "test_id": catalogue["test_id"],
        "appointment_datetime": get_future_datetime(),
    }
    response = client.post("/bookings/", json=payload, headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Diagnostic centre not found"


def test_create_booking_nonexistent_test_returns_404(user_a, catalogue):
    _, headers = user_a
    payload = {
        "centre_id": catalogue["centre_id"],
        "test_id": str(uuid.uuid4()),
        "appointment_datetime": get_future_datetime(),
    }
    response = client.post("/bookings/", json=payload, headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Diagnostic test not found"


def test_create_booking_centre_mismatch_returns_400(user_a, catalogue):
    """Test belongs to Centre A, but booking requested under Centre B."""
    _, headers = user_a

    # Create second centre
    res_b = client.post(
        "/centres/",
        json={
            "name": f"Second Centre {uuid.uuid4().hex[:6]}",
            "location": "Jayanagar, Bangalore",
            "contact_number": "+918025531001",
        },
        headers=headers,
    )
    second_centre_id = res_b.json()["id"]

    # Attempt to book test from Centre A with Centre B
    payload = {
        "centre_id": second_centre_id,
        "test_id": catalogue["test_id"],
        "appointment_datetime": get_future_datetime(),
    }
    response = client.post("/bookings/", json=payload, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Diagnostic test does not belong to the specified centre"


def test_create_booking_inactive_test_returns_400(user_a, catalogue):
    _, headers = user_a

    # Mark diagnostic test as inactive directly in DB
    with SessionLocal() as db:
        test = db.get(DiagnosticTest, uuid.UUID(catalogue["test_id"]))
        test.is_active = False
        db.commit()

    payload = {
        "centre_id": catalogue["centre_id"],
        "test_id": catalogue["test_id"],
        "appointment_datetime": get_future_datetime(),
    }
    response = client.post("/bookings/", json=payload, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Diagnostic test is not currently active"


def test_create_booking_past_datetime_returns_422(user_a, catalogue):
    _, headers = user_a
    past_dt = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    payload = {
        "centre_id": catalogue["centre_id"],
        "test_id": catalogue["test_id"],
        "appointment_datetime": past_dt,
    }
    response = client.post("/bookings/", json=payload, headers=headers)
    assert response.status_code == 422


def test_create_booking_invalid_datetime_format_returns_422(user_a, catalogue):
    _, headers = user_a
    payload = {
        "centre_id": catalogue["centre_id"],
        "test_id": catalogue["test_id"],
        "appointment_datetime": "not-a-datetime",
    }
    response = client.post("/bookings/", json=payload, headers=headers)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 3. Price Snapshot Invariant Tests
# ---------------------------------------------------------------------------

def test_booking_price_snapshot_invariant(user_a, catalogue):
    """Altering the test's price in the database does NOT alter the existing booking's amount."""
    _, headers = user_a

    # 1. Create booking at initial price (450.00)
    payload = {
        "centre_id": catalogue["centre_id"],
        "test_id": catalogue["test_id"],
        "appointment_datetime": get_future_datetime(),
    }
    create_res = client.post("/bookings/", json=payload, headers=headers)
    assert create_res.status_code == 201
    booking_id = create_res.json()["id"]
    assert Decimal(str(create_res.json()["amount"])) == Decimal("450.00")

    # 2. Update test price in the database to 850.00
    with SessionLocal() as db:
        test = db.get(DiagnosticTest, uuid.UUID(catalogue["test_id"]))
        test.price = Decimal("850.00")
        db.commit()

    # 3. Fetch existing booking via GET /bookings/{id}
    fetch_res = client.get(f"/bookings/{booking_id}", headers=headers)
    assert fetch_res.status_code == 200
    # Amount must remain the snapshot price (450.00), not the updated catalogue price (850.00)
    assert Decimal(str(fetch_res.json()["amount"])) == Decimal("450.00")


# ---------------------------------------------------------------------------
# 4. Ownership & Tenant Isolation Tests
# ---------------------------------------------------------------------------

def test_ownership_isolation_listing(user_a, user_b, catalogue):
    user_a_id, headers_a = user_a
    user_b_id, headers_b = user_b

    # User A creates a booking
    res_a = client.post(
        "/bookings/",
        json={
            "centre_id": catalogue["centre_id"],
            "test_id": catalogue["test_id"],
            "appointment_datetime": get_future_datetime(),
        },
        headers=headers_a,
    )
    booking_a_id = res_a.json()["id"]

    # User B creates a booking
    res_b = client.post(
        "/bookings/",
        json={
            "centre_id": catalogue["centre_id"],
            "test_id": catalogue["test_id"],
            "appointment_datetime": get_future_datetime(),
        },
        headers=headers_b,
    )
    booking_b_id = res_b.json()["id"]

    # User A lists bookings: sees booking_a_id, never booking_b_id
    list_a = client.get("/bookings/", headers=headers_a)
    assert list_a.status_code == 200
    ids_a = [b["id"] for b in list_a.json()]
    assert booking_a_id in ids_a
    assert booking_b_id not in ids_a

    # User B lists bookings: sees booking_b_id, never booking_a_id
    list_b = client.get("/bookings/", headers=headers_b)
    assert list_b.status_code == 200
    ids_b = [b["id"] for b in list_b.json()]
    assert booking_b_id in ids_b
    assert booking_a_id not in ids_b


def test_cross_user_booking_access_returns_403(user_a, user_b, catalogue):
    _, headers_a = user_a
    _, headers_b = user_b

    # User A creates a booking
    res_a = client.post(
        "/bookings/",
        json={
            "centre_id": catalogue["centre_id"],
            "test_id": catalogue["test_id"],
            "appointment_datetime": get_future_datetime(),
        },
        headers=headers_a,
    )
    booking_a_id = res_a.json()["id"]

    # User B attempts to access User A's booking
    res_access = client.get(f"/bookings/{booking_a_id}", headers=headers_b)
    assert res_access.status_code == 403
    assert res_access.json()["detail"] == "Access to this booking is forbidden"


def test_cross_user_booking_cancel_returns_403(user_a, user_b, catalogue):
    _, headers_a = user_a
    _, headers_b = user_b

    # User A creates a booking
    res_a = client.post(
        "/bookings/",
        json={
            "centre_id": catalogue["centre_id"],
            "test_id": catalogue["test_id"],
            "appointment_datetime": get_future_datetime(),
        },
        headers=headers_a,
    )
    booking_a_id = res_a.json()["id"]

    # User B attempts to cancel User A's booking
    res_cancel = client.patch(f"/bookings/{booking_a_id}/cancel", headers=headers_b)
    assert res_cancel.status_code == 403
    assert res_cancel.json()["detail"] == "Access to this booking is forbidden"


def test_get_nonexistent_booking_returns_404(user_a):
    _, headers = user_a
    random_id = uuid.uuid4()
    response = client.get(f"/bookings/{random_id}", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


# ---------------------------------------------------------------------------
# 5. Booking State Machine & Transition Tests
# ---------------------------------------------------------------------------

def test_cancel_pending_booking_via_api(user_a, catalogue):
    _, headers = user_a

    # Create booking
    res = client.post(
        "/bookings/",
        json={
            "centre_id": catalogue["centre_id"],
            "test_id": catalogue["test_id"],
            "appointment_datetime": get_future_datetime(),
        },
        headers=headers,
    )
    booking_id = res.json()["id"]
    assert res.json()["status"] == "PENDING"

    # Cancel booking
    cancel_res = client.patch(f"/bookings/{booking_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Cancelling again must fail with 409 Conflict (terminal state)
    cancel_again = client.patch(f"/bookings/{booking_id}/cancel", headers=headers)
    assert cancel_again.status_code == 409
    assert "Cannot transition booking from CANCELLED to CANCELLED" in cancel_again.json()["detail"]


def test_cancel_confirmed_booking_returns_409(user_a, catalogue):
    _, headers = user_a

    # Create booking
    res = client.post(
        "/bookings/",
        json={
            "centre_id": catalogue["centre_id"],
            "test_id": catalogue["test_id"],
            "appointment_datetime": get_future_datetime(),
        },
        headers=headers,
    )
    booking_id = res.json()["id"]

    # Move booking to CONFIRMED directly
    with SessionLocal() as db:
        booking = db.get(Booking, uuid.UUID(booking_id))
        booking.status = BookingStatus.CONFIRMED
        db.commit()

    # Attempt to cancel CONFIRMED booking
    cancel_res = client.patch(f"/bookings/{booking_id}/cancel", headers=headers)
    assert cancel_res.status_code == 409
    assert "Cannot transition booking from CONFIRMED to CANCELLED" in cancel_res.json()["detail"]


def test_cancel_failed_booking_returns_409(user_a, catalogue):
    _, headers = user_a

    # Create booking
    res = client.post(
        "/bookings/",
        json={
            "centre_id": catalogue["centre_id"],
            "test_id": catalogue["test_id"],
            "appointment_datetime": get_future_datetime(),
        },
        headers=headers,
    )
    booking_id = res.json()["id"]

    # Move booking to FAILED directly
    with SessionLocal() as db:
        booking = db.get(Booking, uuid.UUID(booking_id))
        booking.status = BookingStatus.FAILED
        db.commit()

    # Attempt to cancel FAILED booking
    cancel_res = client.patch(f"/bookings/{booking_id}/cancel", headers=headers)
    assert cancel_res.status_code == 409
    assert "Cannot transition booking from FAILED to CANCELLED" in cancel_res.json()["detail"]



def test_service_level_state_transitions(catalogue, user_a):
    user_id, _ = user_a

    with SessionLocal() as db:
        # Create a test booking
        booking = Booking(
            user_id=uuid.UUID(user_id),
            centre_id=uuid.UUID(catalogue["centre_id"]),
            test_id=uuid.UUID(catalogue["test_id"]),
            appointment_datetime=datetime.now(timezone.utc) + timedelta(days=1),
            amount=Decimal("450.00"),
            status=BookingStatus.PENDING,
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

        # 1. PENDING -> CONFIRMED is valid
        transition_booking_status(db, booking, BookingStatus.CONFIRMED)
        assert booking.status == BookingStatus.CONFIRMED

        # 2. CONFIRMED -> PENDING is invalid (terminal)
        with pytest.raises(HTTPException) as exc_info:
            transition_booking_status(db, booking, BookingStatus.PENDING)
        assert exc_info.value.status_code == 409

        # 3. CONFIRMED -> FAILED is invalid (terminal)
        with pytest.raises(HTTPException) as exc_info:
            transition_booking_status(db, booking, BookingStatus.FAILED)
        assert exc_info.value.status_code == 409

        # 4. CONFIRMED -> CANCELLED is invalid (terminal)
        with pytest.raises(HTTPException) as exc_info:
            transition_booking_status(db, booking, BookingStatus.CANCELLED)
        assert exc_info.value.status_code == 409


def test_service_level_failed_is_terminal(catalogue, user_a):
    user_id, _ = user_a

    with SessionLocal() as db:
        booking = Booking(
            user_id=uuid.UUID(user_id),
            centre_id=uuid.UUID(catalogue["centre_id"]),
            test_id=uuid.UUID(catalogue["test_id"]),
            appointment_datetime=datetime.now(timezone.utc) + timedelta(days=1),
            amount=Decimal("450.00"),
            status=BookingStatus.PENDING,
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

        # PENDING -> FAILED is valid
        transition_booking_status(db, booking, BookingStatus.FAILED)
        assert booking.status == BookingStatus.FAILED

        # FAILED -> CONFIRMED is invalid
        with pytest.raises(HTTPException) as exc_info:
            transition_booking_status(db, booking, BookingStatus.CONFIRMED)
        assert exc_info.value.status_code == 409

        # FAILED -> CANCELLED is invalid
        with pytest.raises(HTTPException) as exc_info:
            transition_booking_status(db, booking, BookingStatus.CANCELLED)
        assert exc_info.value.status_code == 409

        # FAILED -> PENDING is invalid
        with pytest.raises(HTTPException) as exc_info:
            transition_booking_status(db, booking, BookingStatus.PENDING)
        assert exc_info.value.status_code == 409


def test_service_level_cancelled_is_terminal(catalogue, user_a):
    user_id, _ = user_a

    with SessionLocal() as db:
        booking = Booking(
            user_id=uuid.UUID(user_id),
            centre_id=uuid.UUID(catalogue["centre_id"]),
            test_id=uuid.UUID(catalogue["test_id"]),
            appointment_datetime=datetime.now(timezone.utc) + timedelta(days=1),
            amount=Decimal("450.00"),
            status=BookingStatus.PENDING,
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

        # PENDING -> CANCELLED is valid
        transition_booking_status(db, booking, BookingStatus.CANCELLED)
        assert booking.status == BookingStatus.CANCELLED

        # CANCELLED -> CONFIRMED is invalid
        with pytest.raises(HTTPException) as exc_info:
            transition_booking_status(db, booking, BookingStatus.CONFIRMED)
        assert exc_info.value.status_code == 409

        # CANCELLED -> FAILED is invalid
        with pytest.raises(HTTPException) as exc_info:
            transition_booking_status(db, booking, BookingStatus.FAILED)
        assert exc_info.value.status_code == 409

        # CANCELLED -> PENDING is invalid
        with pytest.raises(HTTPException) as exc_info:
            transition_booking_status(db, booking, BookingStatus.PENDING)
        assert exc_info.value.status_code == 409


def test_booking_response_does_not_leak_internal_state(user_a, catalogue):
    _, headers = user_a
    res = client.post(
        "/bookings/",
        json={
            "centre_id": catalogue["centre_id"],
            "test_id": catalogue["test_id"],
            "appointment_datetime": get_future_datetime(),
        },
        headers=headers,
    )
    data = res.json()
    internal_keys = {"_sa_instance_state", "password", "metadata"}
    assert internal_keys.isdisjoint(data.keys())
