"""Property model."""

from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from proppilot.database import Base


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    ical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bedrooms: Mapped[int] = mapped_column(Integer, default=1)
    max_guests: Mapped[int] = mapped_column(Integer, default=4)
    base_price: Mapped[float] = mapped_column(Float, default=100.0)
    cleaning_fee: Mapped[float] = mapped_column(Float, default=0.0)
    wifi_password: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lockbox_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    checkout_time: Mapped[str] = mapped_column(String(10), default="11:00")
    checkin_time: Mapped[str] = mapped_column(String(10), default="15:00")
    cleaner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cleaner_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cleaner_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="prop")  # noqa: F821
    cleaning_tasks: Mapped[list["CleaningTask"]] = relationship(back_populates="prop")  # noqa: F821
    maintenance_tasks: Mapped[list["MaintenanceTask"]] = relationship(back_populates="prop")  # noqa: F821
    inventory_items: Mapped[list["InventoryItem"]] = relationship(back_populates="prop")  # noqa: F821
    pricing_rules: Mapped[list["PricingRule"]] = relationship(back_populates="prop")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Property id={self.id} name={self.name!r}>"
