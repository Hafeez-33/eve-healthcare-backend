import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DiagnosticTestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="Test name")
    description: Optional[str] = Field(default=None, description="Optional test description")
    price: Decimal = Field(gt=0, decimal_places=2, description="Price must be strictly positive")


class DiagnosticTestResponse(BaseModel):
    id: uuid.UUID
    centre_id: uuid.UUID
    name: str
    description: Optional[str]
    price: Decimal
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
