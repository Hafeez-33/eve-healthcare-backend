import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_headers():
    """Generates valid Bearer authentication headers for an active database user."""
    unique_email = f"auth_user_{uuid.uuid4().hex[:8]}@example.com"
    signup_res = client.post(
        "/auth/signup",
        json={"email": unique_email, "password": "Password123!", "full_name": "Auth User"},
    )
    user_id = signup_res.json()["id"]
    token = create_access_token(subject=user_id)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------
# Diagnostic Centres Tests
# ---------------------------------------------------------

def test_create_centre_authenticated(auth_headers):
    payload = {
        "name": f"Apollo Clinic {uuid.uuid4().hex[:6]}",
        "location": "Koramangala, Bangalore",
        "contact_number": "+918025531234",
    }
    response = client.post("/centres/", json=payload, headers=auth_headers)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == payload["name"]
    assert data["location"] == payload["location"]
    assert data["contact_number"] == payload["contact_number"]
    assert "id" in data
    assert "created_at" in data
    assert data["tests"] == []


def test_create_centre_unauthenticated_returns_401():
    payload = {
        "name": "Unauthorized Centre",
        "location": "Jayanagar, Bangalore",
        "contact_number": "+918025531235",
    }
    response = client.post("/centres/", json=payload)
    assert response.status_code == 401


def test_create_centre_invalid_input_returns_422(auth_headers):
    # Empty name violates min_length=1
    payload = {
        "name": "",
        "location": "Indiranagar, Bangalore",
        "contact_number": "+918025531236",
    }
    response = client.post("/centres/", json=payload, headers=auth_headers)
    assert response.status_code == 422


def test_list_centres():
    response = client.get("/centres/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_existing_centre(auth_headers):
    # Create centre first
    create_res = client.post(
        "/centres/",
        json={
            "name": f"Centre Details Test {uuid.uuid4().hex[:6]}",
            "location": "Whitefield, Bangalore",
            "contact_number": "+918025531237",
        },
        headers=auth_headers,
    )
    centre_id = create_res.json()["id"]

    # Fetch details
    response = client.get(f"/centres/{centre_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == centre_id
    assert "tests" in data


def test_get_nonexistent_centre_returns_404():
    random_id = uuid.uuid4()
    response = client.get(f"/centres/{random_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Diagnostic centre not found"


def test_get_centre_invalid_uuid_returns_422():
    response = client.get("/centres/not-a-valid-uuid")
    assert response.status_code == 422


# ---------------------------------------------------------
# Diagnostic Tests Catalog Tests
# ---------------------------------------------------------

def test_create_diagnostic_test_authenticated(auth_headers):
    # Create centre
    centre_res = client.post(
        "/centres/",
        json={
            "name": f"Test Lab {uuid.uuid4().hex[:6]}",
            "location": "Malleshwaram, Bangalore",
            "contact_number": "+918025531238",
        },
        headers=auth_headers,
    )
    centre_id = centre_res.json()["id"]

    # Create diagnostic test under centre
    test_payload = {
        "name": "Lipid Profile Test",
        "description": "Measures total cholesterol, HDL, LDL, and triglycerides",
        "price": "650.00",
    }
    response = client.post(
        f"/centres/{centre_id}/tests",
        json=test_payload,
        headers=auth_headers,
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Lipid Profile Test"
    assert data["centre_id"] == centre_id
    assert Decimal(str(data["price"])) == Decimal("650.00")
    assert data["is_active"] is True
    assert "id" in data


def test_create_diagnostic_test_unauthenticated_returns_401():
    random_id = uuid.uuid4()
    response = client.post(
        f"/centres/{random_id}/tests",
        json={"name": "CBC", "price": "300.00"},
    )
    assert response.status_code == 401


def test_create_diagnostic_test_positive_price(auth_headers):
    centre_res = client.post(
        "/centres/",
        json={
            "name": f"Price Lab {uuid.uuid4().hex[:6]}",
            "location": "HSR Layout, Bangalore",
            "contact_number": "+918025531239",
        },
        headers=auth_headers,
    )
    centre_id = centre_res.json()["id"]

    response = client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "Valid Price Test", "price": "199.99"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert Decimal(str(response.json()["price"])) == Decimal("199.99")


def test_create_diagnostic_test_zero_price_returns_422(auth_headers):
    random_id = uuid.uuid4()
    response = client.post(
        f"/centres/{random_id}/tests",
        json={"name": "Zero Price Test", "price": "0.00"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_create_diagnostic_test_negative_price_returns_422(auth_headers):
    random_id = uuid.uuid4()
    response = client.post(
        f"/centres/{random_id}/tests",
        json={"name": "Negative Price Test", "price": "-50.00"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_create_diagnostic_test_nonexistent_centre_returns_404(auth_headers):
    random_id = uuid.uuid4()
    response = client.post(
        f"/centres/{random_id}/tests",
        json={"name": "Orphan Test", "price": "500.00"},
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Diagnostic centre not found"


def test_list_diagnostic_tests_for_centre(auth_headers):
    # Create centre
    centre_res = client.post(
        "/centres/",
        json={
            "name": f"Listing Lab {uuid.uuid4().hex[:6]}",
            "location": "BTM Layout, Bangalore",
            "contact_number": "+918025531240",
        },
        headers=auth_headers,
    )
    centre_id = centre_res.json()["id"]

    # Add two tests
    client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "Test A", "price": "100.00"},
        headers=auth_headers,
    )
    client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "Test B", "price": "200.00"},
        headers=auth_headers,
    )

    response = client.get(f"/centres/{centre_id}/tests")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    names = [t["name"] for t in data]
    assert "Test A" in names
    assert "Test B" in names


def test_list_diagnostic_tests_nonexistent_centre_returns_404():
    random_id = uuid.uuid4()
    response = client.get(f"/centres/{random_id}/tests")
    assert response.status_code == 404
    assert response.json()["detail"] == "Diagnostic centre not found"


def test_duplicate_test_name_same_centre_returns_409(auth_headers):
    centre_res = client.post(
        "/centres/",
        json={
            "name": f"Duplicate Test Lab {uuid.uuid4().hex[:6]}",
            "location": "Marathahalli, Bangalore",
            "contact_number": "+918025531241",
        },
        headers=auth_headers,
    )
    centre_id = centre_res.json()["id"]

    # Add first test
    res1 = client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "Thyroid Stimulating Hormone (TSH)", "price": "400.00"},
        headers=auth_headers,
    )
    assert res1.status_code == 201

    # Add duplicate test name under same centre
    res2 = client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "Thyroid Stimulating Hormone (TSH)", "price": "450.00"},
        headers=auth_headers,
    )
    assert res2.status_code == 409
    assert res2.json()["detail"] == "Diagnostic test with this name already exists at this centre"


def test_same_test_name_different_centres_allowed(auth_headers):
    # Create Centre 1
    centre1 = client.post(
        "/centres/",
        json={
            "name": f"Branch Alpha {uuid.uuid4().hex[:6]}",
            "location": "Rajajinagar, Bangalore",
            "contact_number": "+918025531242",
        },
        headers=auth_headers,
    ).json()

    # Create Centre 2
    centre2 = client.post(
        "/centres/",
        json={
            "name": f"Branch Beta {uuid.uuid4().hex[:6]}",
            "location": "Electronic City, Bangalore",
            "contact_number": "+918025531243",
        },
        headers=auth_headers,
    ).json()

    test_name = "HbA1c Blood Sugar Test"

    # Add same test name to Centre 1 at ₹400
    res1 = client.post(
        f"/centres/{centre1['id']}/tests",
        json={"name": test_name, "price": "400.00"},
        headers=auth_headers,
    )
    assert res1.status_code == 201

    # Add same test name to Centre 2 at ₹450 (centre-specific pricing)
    res2 = client.post(
        f"/centres/{centre2['id']}/tests",
        json={"name": test_name, "price": "450.00"},
        headers=auth_headers,
    )
    assert res2.status_code == 201
    assert Decimal(str(res1.json()["price"])) == Decimal("400.00")
    assert Decimal(str(res2.json()["price"])) == Decimal("450.00")


def test_response_does_not_expose_unexpected_internal_fields(auth_headers):
    centre_res = client.post(
        "/centres/",
        json={
            "name": f"Audit Lab {uuid.uuid4().hex[:6]}",
            "location": "Yelahanka, Bangalore",
            "contact_number": "+918025531244",
        },
        headers=auth_headers,
    )
    data = centre_res.json()
    disallowed_fields = {"_sa_instance_state", "hashed_password", "password", "metadata"}
    assert disallowed_fields.isdisjoint(data.keys())
