"""Tests for calendar sync parsing logic."""

from datetime import date

from icalendar import Calendar

from proppilot.modules.calendar_sync.sync import CalendarSyncer, _parse_ical_date


def test_parse_ical_events(sample_ics: str):
    syncer = CalendarSyncer()
    events = syncer._parse_events(sample_ics)

    assert len(events) == 3

    # First event: John D, Feb 1-5
    assert events[0]["uid"] == "airbnb-abc123@airbnb.com"
    assert events[0]["checkin"] == date(2026, 2, 1)
    assert events[0]["checkout"] == date(2026, 2, 5)
    assert "John D" in events[0]["summary"]

    # Second event: Jane S, Feb 10-12
    assert events[1]["uid"] == "airbnb-def456@airbnb.com"
    assert events[1]["checkin"] == date(2026, 2, 10)
    assert events[1]["checkout"] == date(2026, 2, 12)


def test_parse_ical_date_from_date():
    assert _parse_ical_date(date(2026, 3, 15)) == date(2026, 3, 15)


def test_parse_empty_calendar():
    syncer = CalendarSyncer()
    ical_text = (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "END:VCALENDAR\n"
    )
    events = syncer._parse_events(ical_text)
    assert events == []
