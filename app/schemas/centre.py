import uuid
from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.diagnostic_test import DiagnosticTestResponse


class CentreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="Diagnostic centre name")
    location: str = Field(min_length=1, description="Physical location or address")
    contact_number: str = Field(min_length=1, max_length=25, description="Contact phone number")


class CentreResponse(BaseModel):
    id: uuid.UUID
    name: str
    location: str
    contact_number: str
    created_at: datetime
    tests: List[DiagnosticTestResponse] = Field(
        default_factory=list,
        validation_alias="diagnostic_tests",
        description="Available diagnostic tests offered by this centre",
    )

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )
