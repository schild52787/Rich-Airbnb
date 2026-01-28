"""Tests for operations module — cleaning tasks, maintenance, inventory."""

from datetime import date, datetime, timezone
from unittest.mock import patch

from sqlalchemy.orm import Session

from proppilot.events import Event, EventType
from proppilot.models.booking import Booking
from proppilot.models.property import Property
from proppilot.models.task import CleaningTask, InventoryItem, MaintenanceTask


def test_create_cleaning_task_on_booking(db_session: Session, sample_property: Property, sample_booking: Booking):
    """Creating a cleaning task sets the correct date and links to the booking."""
    from proppilot.modules.operations.ops import OperationsManager

    with patch("proppilot.modules.operations.ops.get_session", return_value=db_session):
        ops = OperationsManager()
        task = ops.create_cleaning_task(sample_booking.id, sample_property.id)

    assert task is not None
    assert task.scheduled_date == sample_booking.checkout_date
    assert task.booking_id == sample_booking.id
    assert task.status == "pending"
    assert task.is_turnover is False
    assert task.priority == "normal"


def test_duplicate_cleaning_task_not_created(db_session: Session, sample_property: Property, sample_booking: Booking):
    """Creating a cleaning task twice returns the existing one."""
    from unittest.mock import patch as _patch
    from proppilot.modules.operations.ops import OperationsManager

    def _noop_close(self):
        pass

    with (
        _patch("proppilot.modules.operations.ops.get_session", return_value=db_session),
        _patch.object(type(db_session), "close", _noop_close),
    ):
        ops = OperationsManager()
        task1 = ops.create_cleaning_task(sample_booking.id, sample_property.id)
        task2 = ops.create_cleaning_task(sample_booking.id, sample_property.id)

    assert task1.id == task2.id
    count = db_session.query(CleaningTask).filter(CleaningTask.booking_id == sample_booking.id).count()
    assert count == 1


def test_same_day_turnover_detected(db_session: Session, sample_property: Property):
    """A booking that checks in on another's checkout date creates a high-priority turnover task."""
    from proppilot.modules.operations.ops import OperationsManager

    # Booking 1: Feb 1-5
    booking1 = Booking(
        property_id=sample_property.id, ical_uid="uid-1@airbnb.com",
        checkin_date=date(2026, 2, 1), checkout_date=date(2026, 2, 5),
        status="confirmed", source="ical",
    )
    # Booking 2: checks in Feb 5 (same day as booking1 checkout)
    booking2 = Booking(
        property_id=sample_property.id, ical_uid="uid-2@airbnb.com",
        checkin_date=date(2026, 2, 5), checkout_date=date(2026, 2, 8),
        status="confirmed", source="ical",
    )
    db_session.add_all([booking1, booking2])
    db_session.commit()

    with patch("proppilot.modules.operations.ops.get_session", return_value=db_session):
        ops = OperationsManager()
        task = ops.create_cleaning_task(booking1.id, sample_property.id)

    assert task is not None
    assert task.is_turnover is True
    assert task.priority == "high"


def test_cancel_cleaning_tasks_on_booking_cancel(db_session: Session, sample_property: Property, sample_booking: Booking):
    """Cancelling a booking cancels associated cleaning tasks."""
    from proppilot.modules.operations.ops import OperationsManager

    # Create a cleaning task first
    task = CleaningTask(
        property_id=sample_property.id, booking_id=sample_booking.id,
        scheduled_date=sample_booking.checkout_date, status="pending",
    )
    db_session.add(task)
    db_session.commit()
    task_id = task.id

    with patch("proppilot.modules.operations.ops.get_session", return_value=db_session):
        ops = OperationsManager()
        event = Event(
            event_type=EventType.BOOKING_CANCELLED,
            data={"booking_id": sample_booking.id},
        )
        ops._on_booking_cancelled(event)

    cancelled_task = db_session.get(CleaningTask, task_id)
    assert cancelled_task.status == "cancelled"


def test_event_handler_creates_cleaning_task(db_session: Session, sample_property: Property, sample_booking: Booking):
    """BOOKING_NEW event handler auto-creates a cleaning task."""
    from proppilot.modules.operations.ops import OperationsManager

    with patch("proppilot.modules.operations.ops.get_session", return_value=db_session):
        ops = OperationsManager()
        event = Event(
            event_type=EventType.BOOKING_NEW,
            data={"booking_id": sample_booking.id, "property_id": sample_property.id},
        )
        ops._on_new_booking(event)

    task = db_session.query(CleaningTask).filter(CleaningTask.booking_id == sample_booking.id).first()
    assert task is not None
    assert task.scheduled_date == sample_booking.checkout_date


def test_create_and_complete_maintenance_task(db_session: Session, sample_property: Property):
    """Maintenance task CRUD: create then complete with cost."""
    from proppilot.modules.operations.ops import OperationsManager

    with patch("proppilot.modules.operations.ops.get_session", return_value=db_session):
        ops = OperationsManager()
        task = ops.create_maintenance_task(
            sample_property.id, "Fix leaky faucet", priority="high", cost=None,
        )
        assert task.status == "open"
        assert task.title == "Fix leaky faucet"

        ops.complete_maintenance_task(task.id, cost=150.0)

    updated = db_session.get(MaintenanceTask, task.id)
    assert updated.status == "completed"
    assert updated.cost == 150.0
    assert updated.completed_at is not None


def test_inventory_reorder_alerts(db_session: Session, sample_property: Property):
    """Inventory check returns items at or below reorder threshold."""
    from proppilot.modules.operations.ops import OperationsManager

    low_item = InventoryItem(
        property_id=sample_property.id, name="Toilet Paper",
        quantity=1, reorder_threshold=5,
    )
    ok_item = InventoryItem(
        property_id=sample_property.id, name="Towels",
        quantity=10, reorder_threshold=3,
    )
    db_session.add_all([low_item, ok_item])
    db_session.commit()

    with patch("proppilot.modules.operations.ops.get_session", return_value=db_session):
        ops = OperationsManager()
        alerts = ops.check_inventory_alerts()

    names = [item.name for item in alerts]
    assert "Toilet Paper" in names
    assert "Towels" not in names
