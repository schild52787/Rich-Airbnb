"""Tests for guest communication module."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from sqlalchemy.orm import Session

from proppilot.events import Event, EventType
from proppilot.models.booking import Booking
from proppilot.models.message import MessageLog, MessageTemplate
from proppilot.models.property import Property


def _noop_close(self):
    """Prevent session.close() from detaching objects during tests."""
    pass


def test_queue_welcome_message(db_session: Session, sample_property: Property, sample_booking: Booking):
    """Queuing a welcome message creates a MessageLog entry."""
    from proppilot.modules.guest_comms.comms import GuestCommunicator

    with (
        patch("proppilot.modules.guest_comms.comms.get_session", return_value=db_session),
        patch.object(type(db_session), "close", _noop_close),
    ):
        comms = GuestCommunicator()
        msg = comms.queue_message(sample_booking.id, "welcome")

    assert msg is not None
    assert msg.template_name == "welcome"
    assert msg.channel == "airbnb"
    assert msg.status == "queued"
    assert "John Doe" in msg.body or "Guest" in msg.body


def test_duplicate_message_not_queued(db_session: Session, sample_property: Property, sample_booking: Booking):
    """Queuing the same template for the same booking twice returns the existing one."""
    from proppilot.modules.guest_comms.comms import GuestCommunicator

    with (
        patch("proppilot.modules.guest_comms.comms.get_session", return_value=db_session),
        patch.object(type(db_session), "close", _noop_close),
    ):
        comms = GuestCommunicator()
        msg1 = comms.queue_message(sample_booking.id, "welcome")
        msg2 = comms.queue_message(sample_booking.id, "welcome")

    assert msg1.id == msg2.id
    count = db_session.query(MessageLog).filter(MessageLog.booking_id == sample_booking.id).count()
    assert count == 1


def test_queue_message_renders_template_context(db_session: Session, sample_property: Property, sample_booking: Booking):
    """Message body includes property and booking details."""
    from proppilot.modules.guest_comms.comms import GuestCommunicator

    with (
        patch("proppilot.modules.guest_comms.comms.get_session", return_value=db_session),
        patch.object(type(db_session), "close", _noop_close),
    ):
        comms = GuestCommunicator()
        msg = comms.queue_message(sample_booking.id, "check_in_instructions")

    assert msg is not None
    # Template should contain property details
    assert sample_property.address in msg.body or sample_property.name in msg.body


def test_queue_message_nonexistent_booking(db_session: Session):
    """Queuing a message for a non-existent booking returns None."""
    from proppilot.modules.guest_comms.comms import GuestCommunicator

    with (
        patch("proppilot.modules.guest_comms.comms.get_session", return_value=db_session),
        patch.object(type(db_session), "close", _noop_close),
    ):
        comms = GuestCommunicator()
        msg = comms.queue_message(9999, "welcome")

    assert msg is None


def test_on_new_booking_queues_welcome(db_session: Session, sample_property: Property, sample_booking: Booking):
    """BOOKING_NEW event triggers welcome message queuing."""
    from proppilot.modules.guest_comms.comms import GuestCommunicator

    with (
        patch("proppilot.modules.guest_comms.comms.get_session", return_value=db_session),
        patch.object(type(db_session), "close", _noop_close),
    ):
        comms = GuestCommunicator()
        event = Event(
            event_type=EventType.BOOKING_NEW,
            data={"booking_id": sample_booking.id, "property_id": sample_property.id},
        )
        comms._on_new_booking(event)

    msg = db_session.query(MessageLog).filter(MessageLog.booking_id == sample_booking.id).first()
    assert msg is not None
    assert msg.template_name == "welcome"
