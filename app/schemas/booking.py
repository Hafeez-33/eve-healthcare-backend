import uuid
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import BookingStatus


class BookingCreate(BaseModel):
    centre_id: uuid.UUID = Field(..., description="UUID of the diagnostic centre")
    test_id: uuid.UUID = Field(..., description="UUID of the diagnostic test")
    appointment_datetime: datetime = Field(
        ...,
        description="Appointment datetime (must be strictly in the future)",
    )

    @field_validator("appointment_datetime")
    @classmethod
    def validate_future_datetime(cls, v: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        v_aware = v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
        if v_aware <= now:
            raise ValueError("Appointment datetime must be strictly in the future")
        return v_aware


class BookingResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    centre_id: uuid.UUID
    test_id: uuid.UUID
    appointment_datetime: datetime
    amount: Decimal
    status: BookingStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
