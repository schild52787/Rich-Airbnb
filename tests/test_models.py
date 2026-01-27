"""Tests for database models."""

from datetime import date

from sqlalchemy.orm import Session

from proppilot.models.booking import Booking
from proppilot.models.expense import SCHEDULE_E_CATEGORIES, Expense
from proppilot.models.property import Property
from proppilot.models.task import CleaningTask, InventoryItem


def test_create_property(db_session: Session):
    prop = Property(name="Beach House", address="456 Ocean Dr", base_price=200.0)
    db_session.add(prop)
    db_session.commit()

    loaded = db_session.query(Property).first()
    assert loaded.name == "Beach House"
    assert loaded.base_price == 200.0


def test_booking_nights(sample_booking: Booking):
    assert sample_booking.nights == 4  # Feb 1 to Feb 5


def test_booking_property_relationship(db_session: Session, sample_booking: Booking):
    booking = db_session.query(Booking).first()
    assert booking.prop is not None
    assert booking.prop.name == "Test Loft"


def test_cleaning_task_creation(db_session: Session, sample_property: Property, sample_booking: Booking):
    task = CleaningTask(
        property_id=sample_property.id,
        booking_id=sample_booking.id,
        scheduled_date=sample_booking.checkout_date,
        status="pending",
    )
    db_session.add(task)
    db_session.commit()

    loaded = db_session.query(CleaningTask).first()
    assert loaded.scheduled_date == date(2026, 2, 5)
    assert loaded.status == "pending"


def test_inventory_needs_reorder():
    item = InventoryItem(
        id=1, property_id=1, name="Towels",
        quantity=1, reorder_threshold=2,
    )
    assert item.needs_reorder is True

    item.quantity = 5
    assert item.needs_reorder is False


def test_expense_categories():
    assert "cleaning_and_maintenance" in SCHEDULE_E_CATEGORIES
    assert "mortgage_interest" in SCHEDULE_E_CATEGORIES
    assert len(SCHEDULE_E_CATEGORIES) > 10


def test_create_expense(db_session: Session, sample_property: Property):
    expense = Expense(
        property_id=sample_property.id,
        category="cleaning_and_maintenance",
        description="Deep clean",
        amount=150.00,
        date=date(2026, 2, 1),
    )
    db_session.add(expense)
    db_session.commit()

    loaded = db_session.query(Expense).first()
    assert loaded.amount == 150.00
    assert loaded.category == "cleaning_and_maintenance"
