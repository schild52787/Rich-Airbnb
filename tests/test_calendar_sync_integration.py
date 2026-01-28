"""Integration tests for calendar sync — full sync with DB."""

from datetime import date
from unittest.mock import patch

from sqlalchemy.orm import Session

from proppilot.models.booking import Booking
from proppilot.models.property import Property


def test_sync_creates_new_bookings(db_session: Session, sample_property: Property, sample_ics: str):
    """Syncing an iCal feed creates bookings in the database."""
    from proppilot.modules.calendar_sync.sync import CalendarSyncer

    sample_property.ical_url = "https://example.com/ical.ics"
    db_session.commit()

    syncer = CalendarSyncer()

    with (
        patch("proppilot.modules.calendar_sync.sync.get_session", return_value=db_session),
        patch.object(syncer, "_fetch_ical", return_value=sample_ics),
    ):
        syncer._sync_property(db_session, sample_property)

    bookings = db_session.query(Booking).filter(Booking.property_id == sample_property.id).all()
    assert len(bookings) == 3  # 3 events in sample.ics
    uids = {b.ical_uid for b in bookings}
    assert "airbnb-abc123@airbnb.com" in uids
    assert "airbnb-def456@airbnb.com" in uids


def test_sync_detects_cancellation(db_session: Session, sample_property: Property):
    """A booking removed from the iCal feed gets marked as cancelled."""
    from proppilot.modules.calendar_sync.sync import CalendarSyncer

    # Pre-populate a booking that won't appear in the empty feed
    booking = Booking(
        property_id=sample_property.id, ical_uid="removed-uid@airbnb.com",
        checkin_date=date(2026, 3, 1), checkout_date=date(2026, 3, 5),
        status="confirmed", source="ical",
    )
    db_session.add(booking)
    db_session.commit()

    empty_ics = "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"
    syncer = CalendarSyncer()

    with (
        patch("proppilot.modules.calendar_sync.sync.get_session", return_value=db_session),
        patch.object(syncer, "_fetch_ical", return_value=empty_ics),
    ):
        syncer._sync_property(db_session, sample_property)

    cancelled = db_session.get(Booking, booking.id)
    assert cancelled.status == "cancelled"


def test_sync_detects_modification(db_session: Session, sample_property: Property, sample_ics: str):
    """A booking with changed dates is updated and detected as modified."""
    from proppilot.modules.calendar_sync.sync import CalendarSyncer

    # Pre-populate with old dates
    booking = Booking(
        property_id=sample_property.id, ical_uid="airbnb-abc123@airbnb.com",
        checkin_date=date(2026, 1, 15), checkout_date=date(2026, 1, 20),
        status="confirmed", source="ical",
    )
    db_session.add(booking)
    db_session.commit()

    syncer = CalendarSyncer()

    with (
        patch("proppilot.modules.calendar_sync.sync.get_session", return_value=db_session),
        patch.object(syncer, "_fetch_ical", return_value=sample_ics),
    ):
        syncer._sync_property(db_session, sample_property)

    updated = db_session.query(Booking).filter(Booking.ical_uid == "airbnb-abc123@airbnb.com").first()
    # Should now have the sample.ics dates
    assert updated.checkin_date == date(2026, 2, 1)
    assert updated.checkout_date == date(2026, 2, 5)


def test_sync_idempotent(db_session: Session, sample_property: Property, sample_ics: str):
    """Running sync twice with the same data doesn't create duplicates."""
    from proppilot.modules.calendar_sync.sync import CalendarSyncer

    sample_property.ical_url = "https://example.com/ical.ics"
    db_session.commit()

    syncer = CalendarSyncer()

    with (
        patch("proppilot.modules.calendar_sync.sync.get_session", return_value=db_session),
        patch.object(syncer, "_fetch_ical", return_value=sample_ics),
    ):
        syncer._sync_property(db_session, sample_property)
        syncer._sync_property(db_session, sample_property)

    count = db_session.query(Booking).filter(Booking.property_id == sample_property.id).count()
    assert count == 3  # Still only 3
