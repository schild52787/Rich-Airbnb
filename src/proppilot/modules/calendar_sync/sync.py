"""iCal feed fetching, parsing, and booking diff logic."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx
from icalendar import Calendar
from sqlalchemy.orm import Session

from proppilot.database import get_session
from proppilot.events import Event, EventType, event_bus
from proppilot.models.booking import Booking
from proppilot.models.property import Property

logger = logging.getLogger(__name__)


def _parse_ical_date(dt_value) -> date:
    """Convert an icalendar date/datetime to a Python date."""
    if isinstance(dt_value, datetime):
        return dt_value.date()
    if isinstance(dt_value, date):
        return dt_value
    # dt property from icalendar
    dt = dt_value.dt
    if isinstance(dt, datetime):
        return dt.date()
    return dt


class CalendarSyncer:
    """Fetches iCal feeds and syncs bookings to the database."""

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=30, follow_redirects=True)

    def sync_all(self) -> None:
        """Sync all properties that have iCal URLs configured."""
        session = get_session()
        try:
            properties = session.query(Property).filter(Property.ical_url.isnot(None)).all()
            for prop in properties:
                try:
                    self._sync_property(session, prop)
                except Exception:
                    logger.exception("Failed to sync calendar for property %s", prop.name)
        finally:
            session.close()

    def sync_property_by_id(self, property_id: int) -> None:
        """Sync a single property by ID."""
        session = get_session()
        try:
            prop = session.get(Property, property_id)
            if prop and prop.ical_url:
                self._sync_property(session, prop)
        finally:
            session.close()

    def _sync_property(self, session: Session, prop: Property) -> None:
        """Fetch and sync iCal for one property."""
        logger.info("Syncing calendar for property: %s", prop.name)
        ical_text = self._fetch_ical(prop.ical_url)
        if not ical_text:
            return

        events = self._parse_events(ical_text)
        existing_bookings = (
            session.query(Booking)
            .filter(Booking.property_id == prop.id, Booking.source == "ical")
            .all()
        )
        existing_by_uid = {b.ical_uid: b for b in existing_bookings if b.ical_uid}

        seen_uids: set[str] = set()

        for evt in events:
            uid = evt["uid"]
            seen_uids.add(uid)

            if uid in existing_by_uid:
                booking = existing_by_uid[uid]
                changed = self._update_if_changed(booking, evt)
                if changed:
                    session.commit()
                    event_bus.publish(Event(
                        event_type=EventType.BOOKING_MODIFIED,
                        data={"booking_id": booking.id, "property_id": prop.id},
                    ))
            else:
                booking = Booking(
                    property_id=prop.id,
                    ical_uid=uid,
                    checkin_date=evt["checkin"],
                    checkout_date=evt["checkout"],
                    summary=evt.get("summary"),
                    status="confirmed",
                    source="ical",
                )
                session.add(booking)
                session.commit()
                logger.info(
                    "New booking detected: %s, %s to %s",
                    prop.name, evt["checkin"], evt["checkout"],
                )
                event_bus.publish(Event(
                    event_type=EventType.BOOKING_NEW,
                    data={"booking_id": booking.id, "property_id": prop.id},
                ))

        # Detect cancellations: bookings in DB but no longer in feed
        for uid, booking in existing_by_uid.items():
            if uid not in seen_uids and booking.status == "confirmed":
                booking.status = "cancelled"
                session.commit()
                logger.info("Booking cancelled (removed from iCal): %s", booking)
                event_bus.publish(Event(
                    event_type=EventType.BOOKING_CANCELLED,
                    data={"booking_id": booking.id, "property_id": prop.id},
                ))

    def _fetch_ical(self, url: str) -> str | None:
        """Fetch iCal data from URL."""
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError:
            logger.exception("Failed to fetch iCal from %s", url)
            return None

    def _parse_events(self, ical_text: str) -> list[dict]:
        """Parse iCal text into a list of event dicts."""
        cal = Calendar.from_ical(ical_text)
        events = []
        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            uid = str(component.get("uid", ""))
            dtstart = component.get("dtstart")
            dtend = component.get("dtend")
            summary = str(component.get("summary", ""))

            if not uid or not dtstart or not dtend:
                continue

            events.append({
                "uid": uid,
                "checkin": _parse_ical_date(dtstart),
                "checkout": _parse_ical_date(dtend),
                "summary": summary,
            })
        return events

    def _update_if_changed(self, booking: Booking, evt: dict) -> bool:
        """Update booking if iCal data has changed. Returns True if updated."""
        changed = False
        if booking.checkin_date != evt["checkin"]:
            booking.checkin_date = evt["checkin"]
            changed = True
        if booking.checkout_date != evt["checkout"]:
            booking.checkout_date = evt["checkout"]
            changed = True
        if booking.summary != evt.get("summary"):
            booking.summary = evt.get("summary")
            changed = True
        if changed:
            booking.updated_at = datetime.now(timezone.utc)
        return changed
