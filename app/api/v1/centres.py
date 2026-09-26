import uuid
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.centre import CentreCreate, CentreResponse
from app.schemas.diagnostic_test import DiagnosticTestCreate, DiagnosticTestResponse
from app.services.centre_service import create_centre, get_centre_by_id, list_centres
from app.services.diagnostic_test_service import (
    create_diagnostic_test,
    list_tests_by_centre,
)

router = APIRouter(prefix="/centres", tags=["Diagnostic Centres & Tests"])


@router.get(
    "/",
    response_model=List[CentreResponse],
    status_code=status.HTTP_200_OK,
    summary="List available diagnostic centres",
)
def get_all_centres(
    skip: int = Query(0, ge=0, description="Pagination skip"),
    limit: int = Query(100, ge=1, le=100, description="Pagination limit"),
    db: Session = Depends(get_db),
):
    """Retrieve all diagnostic centres and their offered tests."""
    return list_centres(db, skip=skip, limit=limit)


@router.get(
    "/{id}",
    response_model=CentreResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single diagnostic centre by ID",
)
def get_centre(
    id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Retrieve details of a single diagnostic centre, including tests offered."""
    return get_centre_by_id(db, centre_id=id)


@router.post(
    "/",
    response_model=CentreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new diagnostic centre",
)
def create_new_centre(
    data: CentreCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a diagnostic centre. Requires Bearer JWT authentication."""
    return create_centre(db, data=data)


@router.get(
    "/{id}/tests",
    response_model=List[DiagnosticTestResponse],
    status_code=status.HTTP_200_OK,
    summary="List tests offered by a specific diagnostic centre",
)
def get_centre_tests(
    id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Retrieve all diagnostic tests offered by the given diagnostic centre."""
    return list_tests_by_centre(db, centre_id=id)


@router.post(
    "/{id}/tests",
    response_model=DiagnosticTestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a diagnostic test to a diagnostic centre",
)
def add_test_to_centre(
    id: uuid.UUID,
    data: DiagnosticTestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a diagnostic test with centre-specific pricing to the specified centre. Requires Bearer JWT authentication."""
    return create_diagnostic_test(db, centre_id=id, data=data)
