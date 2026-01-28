"""Booking model."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from proppilot.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    ical_uid: Mapped[str | None] = mapped_column(String(500), unique=True, nullable=True)
    confirmation_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    guest_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    guest_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    guest_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    checkin_date: Mapped[date] = mapped_column(Date, nullable=False)
    checkout_date: Mapped[date] = mapped_column(Date, nullable=False)
    num_guests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_payout: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="confirmed")  # confirmed, cancelled, completed
    source: Mapped[str] = mapped_column(String(50), default="ical")  # ical, email, manual
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # Raw iCal summary
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    prop: Mapped["Property"] = relationship(back_populates="bookings")  # noqa: F821
    cleaning_tasks: Mapped[list["CleaningTask"]] = relationship(back_populates="booking")  # noqa: F821
    messages: Mapped[list["MessageLog"]] = relationship(back_populates="booking")  # noqa: F821
    payouts: Mapped[list["Payout"]] = relationship(back_populates="booking")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<Booking id={self.id} property_id={self.property_id} "
            f"guest={self.guest_name!r} {self.checkin_date}..{self.checkout_date}>"
        )

    @property
    def nights(self) -> int:
        return (self.checkout_date - self.checkin_date).days
