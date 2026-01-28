"""Payout and email processing log models."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from proppilot.database import Base


class Payout(Base):
    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payout_date: Mapped[date] = mapped_column(Date, nullable=False)
    confirmation_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="email")  # email, manual
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    booking: Mapped["Booking | None"] = relationship(back_populates="payouts")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Payout id={self.id} ${self.amount:.2f} date={self.payout_date}>"


class EmailProcessingLog(Base):
    __tablename__ = "email_processing_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sender: Mapped[str | None] = mapped_column(String(200), nullable=True)
    received_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    parsed_type: Mapped[str | None] = mapped_column(String(100), nullable=True)  # booking_confirmation, payout, cancellation, unknown
    parsed_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    status: Mapped[str] = mapped_column(String(50), default="processed")  # processed, unrecognized, error
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
