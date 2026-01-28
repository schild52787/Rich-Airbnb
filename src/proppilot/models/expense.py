"""Expense model with IRS Schedule E categories."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from proppilot.database import Base

# IRS Schedule E expense categories
SCHEDULE_E_CATEGORIES = [
    "advertising",
    "auto_and_travel",
    "cleaning_and_maintenance",
    "commissions",
    "insurance",
    "legal_and_professional",
    "management_fees",
    "mortgage_interest",
    "other_interest",
    "repairs",
    "supplies",
    "taxes",
    "utilities",
    "depreciation",
    "other",
]


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_months: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Every N months
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<Expense id={self.id} {self.category} ${self.amount:.2f}>"
