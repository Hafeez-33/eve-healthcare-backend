import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import BookingStatus

if TYPE_CHECKING:
    from app.models.diagnostic_centre import DiagnosticCentre
    from app.models.diagnostic_test import DiagnosticTest
    from app.models.payment import Payment
    from app.models.user import User
    from app.models.webhook_event import WebhookEvent


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    centre_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("diagnostic_centres.id", ondelete="RESTRICT"),
        nullable=False,
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("diagnostic_tests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    appointment_datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", native_enum=True),
        nullable=False,
        default=BookingStatus.PENDING,
        server_default=text("'PENDING'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="bookings",
    )
    centre: Mapped["DiagnosticCentre"] = relationship(
        "DiagnosticCentre",
        back_populates="bookings",
    )
    test: Mapped["DiagnosticTest"] = relationship(
        "DiagnosticTest",
        back_populates="bookings",
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="booking",
    )
    webhook_events: Mapped[List["WebhookEvent"]] = relationship(
        "WebhookEvent",
        back_populates="booking",
    )

    __table_args__ = (
        Index("ix_bookings_user_id", "user_id"),
        Index("ix_bookings_status", "status"),
        Index("ix_bookings_appointment", "appointment_datetime"),
    )
