from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse
from app.services.auth_service import authenticate_user, register_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new patient/user",
)
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    """Create a new user account with email, password, and full name."""
    return register_user(db, request)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User login and JWT access token issuance",
)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email and password to receive a Bearer JWT access token."""
    return authenticate_user(db, request)
