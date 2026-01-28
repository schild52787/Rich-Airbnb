"""Cleaning tasks, maintenance tasks, inventory, and pricing models."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from proppilot.database import Base


class CleaningTask(Base):
    __tablename__ = "cleaning_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, notified, completed, cancelled
    is_turnover: Mapped[bool] = mapped_column(Boolean, default=False)  # Same-day turnover
    priority: Mapped[str] = mapped_column(String(20), default="normal")  # normal, high
    cleaner_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    cleaner_notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    prop: Mapped["Property"] = relationship(back_populates="cleaning_tasks")  # noqa: F821
    booking: Mapped["Booking | None"] = relationship(back_populates="cleaning_tasks")  # noqa: F821

    def __repr__(self) -> str:
        return f"<CleaningTask id={self.id} date={self.scheduled_date} status={self.status!r}>"


class MaintenanceTask(Base):
    __tablename__ = "maintenance_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="open")  # open, in_progress, completed
    priority: Mapped[str] = mapped_column(String(20), default="normal")  # low, normal, high, urgent
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    prop: Mapped["Property"] = relationship(back_populates="maintenance_tasks")  # noqa: F821

    def __repr__(self) -> str:
        return f"<MaintenanceTask id={self.id} title={self.title!r} status={self.status!r}>"


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    reorder_threshold: Mapped[int] = mapped_column(Integer, default=2)
    unit_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    prop: Mapped["Property"] = relationship(back_populates="inventory_items")  # noqa: F821

    @property
    def needs_reorder(self) -> bool:
        return self.quantity <= self.reorder_threshold


class PricingRule(Base):
    __tablename__ = "pricing_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)  # seasonal, day_of_week, lead_time, event
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    days_of_week: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g., "4,5" for Fri/Sat
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    prop: Mapped["Property"] = relationship(back_populates="pricing_rules")  # noqa: F821


class PriceOverride(Base):
    __tablename__ = "price_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
