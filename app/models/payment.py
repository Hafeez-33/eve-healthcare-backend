import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import PaymentStatus

if TYPE_CHECKING:
    from app.models.booking import Booking


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    transaction_reference: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=True),
        nullable=False,
    )
    payment_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="SIMULATED",
        server_default=text("'SIMULATED'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    booking: Mapped["Booking"] = relationship(
        "Booking",
        back_populates="payments",
    )

    __table_args__ = (
        Index("ix_payments_booking_id", "booking_id"),
        Index("ix_payments_txn_ref", "transaction_reference", unique=True),
    )
