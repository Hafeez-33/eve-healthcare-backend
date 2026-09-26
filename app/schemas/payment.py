import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PaymentStatus


class PaymentCreate(BaseModel):
    booking_id: uuid.UUID = Field(..., description="UUID of the booking to pay for")
    simulate_status: PaymentStatus = Field(
        default=PaymentStatus.SUCCESS,
        description="Simulated payment outcome: SUCCESS or FAILED",
    )


class PaymentResponse(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    transaction_reference: str
    amount: Decimal
    status: PaymentStatus
    payment_method: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookPaymentData(BaseModel):
    transaction_reference: str = Field(..., min_length=1, max_length=100)
    booking_id: uuid.UUID
    amount: Decimal = Field(..., gt=0)
    status: PaymentStatus


class WebhookPayload(BaseModel):
    event_id: str = Field(..., min_length=1, max_length=100)
    event_type: str = Field(..., min_length=1, max_length=50)
    timestamp: Optional[datetime] = None
    data: WebhookPaymentData


class WebhookResponse(BaseModel):
    status: str
    event_id: str
    booking_status: Optional[str] = None
