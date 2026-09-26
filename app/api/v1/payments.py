from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.payment import (
    PaymentCreate,
    PaymentResponse,
    WebhookPayload,
    WebhookResponse,
)
from app.services.payment_service import (
    create_simulated_payment,
    process_webhook,
)

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "/",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Simulate direct payment for a pending booking",
)
def create_payment(
    data: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Simulate a direct payment (SUCCESS or FAILED) for a user's pending booking."""
    return create_simulated_payment(db, user_id=current_user.id, data=data)


@router.post(
    "/webhook/",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Process payment gateway webhook callback",
)
def handle_payment_webhook(
    payload: WebhookPayload,
    db: Session = Depends(get_db),
):
    """Process an asynchronous webhook callback from the payment provider with atomic idempotency."""
    return process_webhook(db, payload=payload)
