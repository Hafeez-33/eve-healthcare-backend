import uuid
from datetime import timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.main import app
from app.models.user import User

client = TestClient(app)


@pytest.fixture
def db():
    """Provides a transactional database session rolled back after test completion."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ---------------------------------------------------------
# Password Security Tests
# ---------------------------------------------------------

def test_password_hashing_and_verification():
    raw_password = "SecurePassword123!"
    hashed = hash_password(raw_password)

    # 1. Plaintext must never equal stored hash
    assert raw_password != hashed

    # 2. Correct password verification succeeds
    assert verify_password(raw_password, hashed) is True

    # 3. Wrong password verification fails
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False


# ---------------------------------------------------------
# Signup Endpoint Tests (POST /auth/signup)
# ---------------------------------------------------------

def test_signup_success(db):
    unique_email = f"signup_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": unique_email,
        "password": "StrongPassword123!",
        "full_name": "Alice Smith",
    }
    response = client.post("/auth/signup", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["email"] == unique_email.lower()
    assert data["full_name"] == "Alice Smith"
    assert "id" in data
    assert "created_at" in data
    assert "hashed_password" not in data
    assert "password" not in data

    # Verify directly in PostgreSQL that password is encrypted
    stored_user = db.scalar(select(User).where(User.email == unique_email.lower()))
    assert stored_user is not None
    assert stored_user.hashed_password != payload["password"]
    assert verify_password(payload["password"], stored_user.hashed_password) is True


def test_signup_invalid_email():
    payload = {
        "email": "invalid-email-format",
        "password": "ValidPassword123!",
        "full_name": "Bob Jones",
    }
    response = client.post("/auth/signup", json=payload)
    assert response.status_code == 422


def test_signup_invalid_password():
    payload = {
        "email": f"short_pwd_{uuid.uuid4().hex[:6]}@example.com",
        "password": "short",  # Less than 8 characters
        "full_name": "Charlie Brown",
    }
    response = client.post("/auth/signup", json=payload)
    assert response.status_code == 422


def test_signup_duplicate_email():
    email = f"duplicate_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "password": "Password12345!",
        "full_name": "First User",
    }
    # First signup
    res1 = client.post("/auth/signup", json=payload)
    assert res1.status_code == 201

    # Second signup with same email
    res2 = client.post("/auth/signup", json=payload)
    assert res2.status_code == 409
    assert res2.json()["detail"] == "Email already registered"


def test_signup_email_case_normalization():
    unique_suffix = uuid.uuid4().hex[:8]
    mixed_cased_email = f"MixedCase_{unique_suffix}@Example.COM"
    lower_cased_email = mixed_cased_email.lower()

    payload = {
        "email": mixed_cased_email,
        "password": "Password12345!",
        "full_name": "Case Sensitive User",
    }
    res1 = client.post("/auth/signup", json=payload)
    assert res1.status_code == 201
    assert res1.json()["email"] == lower_cased_email

    # Attempting to sign up with lowercase version should trigger duplicate 409
    payload_lower = {
        "email": lower_cased_email,
        "password": "Password12345!",
        "full_name": "Duplicate Case User",
    }
    res2 = client.post("/auth/signup", json=payload_lower)
    assert res2.status_code == 409


# ---------------------------------------------------------
# Login Endpoint Tests (POST /auth/login)
# ---------------------------------------------------------

def test_login_success():
    email = f"login_success_{uuid.uuid4().hex[:8]}@example.com"
    password = "CorrectPassword123!"

    # Create user
    signup_res = client.post(
        "/auth/signup",
        json={"email": email, "password": password, "full_name": "Login Tester"},
    )
    assert signup_res.status_code == 201

    # Login
    login_res = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"


def test_login_email_case_insensitive():
    email = f"case_login_{uuid.uuid4().hex[:8]}@example.com"
    password = "Password12345!"

    client.post(
        "/auth/signup",
        json={"email": email, "password": password, "full_name": "Case User"},
    )

    # Login with uppercase email
    login_res = client.post(
        "/auth/login",
        json={"email": email.upper(), "password": password},
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()


def test_login_wrong_password_returns_401():
    email = f"wrong_pwd_{uuid.uuid4().hex[:8]}@example.com"
    password = "Password12345!"

    client.post(
        "/auth/signup",
        json={"email": email, "password": password, "full_name": "Wrong Pwd User"},
    )

    login_res = client.post(
        "/auth/login",
        json={"email": email, "password": "IncorrectPassword!"},
    )
    assert login_res.status_code == 401
    assert login_res.json()["detail"] == "Invalid email or password"


def test_login_unknown_email_returns_401():
    login_res = client.post(
        "/auth/login",
        json={"email": "nonexistent_user@example.com", "password": "Password12345!"},
    )
    assert login_res.status_code == 401
    assert login_res.json()["detail"] == "Invalid email or password"


# ---------------------------------------------------------
# JWT Token Structure & Security Tests
# ---------------------------------------------------------

def test_jwt_contains_valid_subject_and_expiration():
    test_user_id = uuid.uuid4()
    token = create_access_token(subject=test_user_id)

    payload = decode_access_token(token)
    assert payload["sub"] == str(test_user_id)
    assert "exp" in payload
    assert "iat" in payload
    assert payload["exp"] > payload["iat"]


def test_jwt_tampered_signature_fails():
    token = create_access_token(subject=uuid.uuid4())
    # Tamper with token string
    tampered_token = token[:-4] + "abcd"

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered_token)


def test_jwt_wrong_secret_fails():
    payload = {"sub": str(uuid.uuid4()), "exp": 9999999999}
    fake_token = jwt.encode(payload, "wrong-secret-key-at-least-32-chars-long", algorithm="HS256")

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(fake_token)


def test_jwt_expired_token_fails():
    expired_token = create_access_token(
        subject=uuid.uuid4(),
        expires_delta=timedelta(seconds=-10),
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired_token)


# ---------------------------------------------------------
# Current User Dependency Tests (get_current_user)
# ---------------------------------------------------------

def test_get_current_user_valid_jwt_resolves_user(db):
    user = User(
        email=f"auth_dep_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="Resolved User",
    )
    db.add(user)
    db.commit()

    token = create_access_token(subject=user.id)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    resolved_user = get_current_user(auth_credentials=credentials, db=db)
    assert resolved_user.id == user.id
    assert resolved_user.email == user.email


def test_get_current_user_missing_credentials_returns_401(db):
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(auth_credentials=None, db=db)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"


def test_get_current_user_invalid_scheme_returns_401(db):
    credentials = HTTPAuthorizationCredentials(scheme="Basic", credentials="mock-token")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(auth_credentials=credentials, db=db)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"


def test_get_current_user_expired_jwt_returns_401(db):
    expired_token = create_access_token(
        subject=uuid.uuid4(),
        expires_delta=timedelta(seconds=-1),
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired_token)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(auth_credentials=credentials, db=db)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token has expired"


def test_get_current_user_missing_sub_returns_401(db):
    # Craft token without 'sub' claim
    token = jwt.encode(
        {"iat": 1000, "exp": 9999999999},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(auth_credentials=credentials, db=db)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token subject claim missing"


def test_get_current_user_invalid_uuid_sub_returns_401(db):
    # Craft token with non-UUID subject
    token = jwt.encode(
        {"sub": "invalid-uuid-string", "exp": 9999999999},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(auth_credentials=credentials, db=db)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"


def test_get_current_user_unknown_user_returns_401(db):
    random_user_id = uuid.uuid4()
    token = create_access_token(subject=random_user_id)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(auth_credentials=credentials, db=db)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "User not found"
