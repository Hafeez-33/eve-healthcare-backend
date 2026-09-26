import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.diagnostic_test import DiagnosticTest


class DiagnosticCentre(Base):
    __tablename__ = "diagnostic_centres"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    location: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    contact_number: Mapped[str] = mapped_column(
        String(25),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    diagnostic_tests: Mapped[List["DiagnosticTest"]] = relationship(
        "DiagnosticTest",
        back_populates="centre",
    )
    bookings: Mapped[List["Booking"]] = relationship(
        "Booking",
        back_populates="centre",
    )

    __table_args__ = (
        Index("ix_centres_name", "name"),
    )
