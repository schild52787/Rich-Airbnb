"""End-to-end tests for event-driven workflows."""

from datetime import date
from unittest.mock import patch

from sqlalchemy.orm import Session

from proppilot.events import Event, EventBus, EventType
from proppilot.models.booking import Booking
from proppilot.models.message import MessageLog
from proppilot.models.property import Property
from proppilot.models.task import CleaningTask


def _noop_close(self):
    pass


def test_new_booking_triggers_cleaning_and_welcome(db_session: Session, sample_property: Property):
    """BOOKING_NEW event triggers both a cleaning task and a welcome message."""
    from proppilot.modules.guest_comms.comms import GuestCommunicator
    from proppilot.modules.operations.ops import OperationsManager

    booking = Booking(
        property_id=sample_property.id, ical_uid="e2e-test@airbnb.com",
        guest_name="Alice Smith", checkin_date=date(2026, 3, 1),
        checkout_date=date(2026, 3, 5), status="confirmed", source="ical",
    )
    db_session.add(booking)
    db_session.commit()

    # Create a local event bus for isolation
    test_bus = EventBus()

    with (
        patch("proppilot.modules.guest_comms.comms.get_session", return_value=db_session),
        patch("proppilot.modules.guest_comms.comms.event_bus", test_bus),
        patch("proppilot.modules.operations.ops.get_session", return_value=db_session),
        patch("proppilot.modules.operations.ops.event_bus", test_bus),
        patch.object(type(db_session), "close", _noop_close),
    ):
        comms = GuestCommunicator()
        ops = OperationsManager()

        # Wire handlers to the test bus
        test_bus.subscribe(EventType.BOOKING_NEW, comms._on_new_booking)
        test_bus.subscribe(EventType.BOOKING_NEW, ops._on_new_booking)

        # Simulate what CalendarSyncer would publish
        test_bus.publish(Event(
            event_type=EventType.BOOKING_NEW,
            data={"booking_id": booking.id, "property_id": sample_property.id},
        ))

    # Verify cleaning task was created
    task = db_session.query(CleaningTask).filter(CleaningTask.booking_id == booking.id).first()
    assert task is not None
    assert task.scheduled_date == date(2026, 3, 5)

    # Verify welcome message was queued
    msg = db_session.query(MessageLog).filter(
        MessageLog.booking_id == booking.id,
        MessageLog.template_name == "welcome",
    ).first()
    assert msg is not None
    assert msg.status == "queued"
    assert "Alice Smith" in msg.body


def test_booking_cancellation_cascades(db_session: Session, sample_property: Property):
    """BOOKING_CANCELLED event cancels cleaning tasks."""
    from proppilot.modules.operations.ops import OperationsManager

    booking = Booking(
        property_id=sample_property.id, ical_uid="cancel-test@airbnb.com",
        checkin_date=date(2026, 4, 1), checkout_date=date(2026, 4, 5),
        status="confirmed", source="ical",
    )
    db_session.add(booking)
    db_session.commit()

    # Create cleaning task
    task = CleaningTask(
        property_id=sample_property.id, booking_id=booking.id,
        scheduled_date=date(2026, 4, 5), status="pending",
    )
    db_session.add(task)
    db_session.commit()

    test_bus = EventBus()

    with (
        patch("proppilot.modules.operations.ops.get_session", return_value=db_session),
        patch("proppilot.modules.operations.ops.event_bus", test_bus),
        patch.object(type(db_session), "close", _noop_close),
    ):
        ops = OperationsManager()
        test_bus.subscribe(EventType.BOOKING_CANCELLED, ops._on_booking_cancelled)

        test_bus.publish(Event(
            event_type=EventType.BOOKING_CANCELLED,
            data={"booking_id": booking.id},
        ))

    updated_task = db_session.get(CleaningTask, task.id)
    assert updated_task.status == "cancelled"
