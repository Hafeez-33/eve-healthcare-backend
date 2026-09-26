import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.diagnostic_centre import DiagnosticCentre


class DiagnosticTest(Base):
    __tablename__ = "diagnostic_tests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    centre_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("diagnostic_centres.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    centre: Mapped["DiagnosticCentre"] = relationship(
        "DiagnosticCentre",
        back_populates="diagnostic_tests",
    )
    bookings: Mapped[List["Booking"]] = relationship(
        "Booking",
        back_populates="test",
    )

    __table_args__ = (
        CheckConstraint("price > 0", name="chk_diagnostic_tests_price_positive"),
        UniqueConstraint("centre_id", "name", name="uq_diagnostic_tests_centre_name"),
        Index("ix_tests_centre_id", "centre_id"),
    )
