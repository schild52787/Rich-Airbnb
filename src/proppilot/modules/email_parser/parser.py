"""IMAP client + Airbnb email pattern matching."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone

from imap_tools import AND, MailBox, MailMessage
from sqlalchemy.orm import Session

from proppilot.config import get_env
from proppilot.database import get_session
from proppilot.events import Event, EventType, event_bus
from proppilot.models.booking import Booking
from proppilot.models.payout import EmailProcessingLog, Payout

logger = logging.getLogger(__name__)

# Airbnb sender patterns
AIRBNB_SENDERS = [
    "automated@airbnb.com",
    "express@airbnb.com",
    "noreply@airbnb.com",
]

# Subject line patterns
PATTERNS = {
    "booking_confirmation": re.compile(
        r"(?:Reservation confirmed|Booking confirmed|You have a new reservation)",
        re.IGNORECASE,
    ),
    "payout": re.compile(
        r"(?:payout|payment.*(?:sent|processed|completed))",
        re.IGNORECASE,
    ),
    "cancellation": re.compile(
        r"(?:cancel|cancelled|cancellation)",
        re.IGNORECASE,
    ),
    "guest_message": re.compile(
        r"(?:message from|sent you a message)",
        re.IGNORECASE,
    ),
}

# Extraction patterns for email body
CONFIRMATION_CODE_RE = re.compile(r"(?:Confirmation code|confirmation code)[:\s]*([A-Z0-9]{8,12})", re.IGNORECASE)
GUEST_NAME_RE = re.compile(r"(?:Guest|from)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)")
PAYOUT_AMOUNT_RE = re.compile(r"\$\s*([\d,]+\.?\d*)")
CHECKIN_DATE_RE = re.compile(r"(?:Check-in|Checkin|Arrival)[:\s]*(\w+ \d{1,2},?\s*\d{4})", re.IGNORECASE)
CHECKOUT_DATE_RE = re.compile(r"(?:Check-out|Checkout|Departure)[:\s]*(\w+ \d{1,2},?\s*\d{4})", re.IGNORECASE)


def _try_parse_date(text: str) -> date | None:
    """Try to parse a date string in common formats."""
    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


class AirbnbEmailParser:
    """Connects to IMAP and parses Airbnb notification emails."""

    def __init__(self) -> None:
        self.host = get_env("IMAP_HOST", "imap.gmail.com")
        self.user = get_env("IMAP_USER")
        self.password = get_env("IMAP_PASSWORD")

    @property
    def is_configured(self) -> bool:
        return bool(self.user and self.password)

    def check_emails(self) -> None:
        """Check for new Airbnb emails and process them."""
        if not self.is_configured:
            logger.warning("IMAP not configured, skipping email check")
            return

        session = get_session()
        try:
            with MailBox(self.host).login(self.user, self.password) as mailbox:
                # Fetch emails from Airbnb senders, unseen only
                criteria = AND(from_=AIRBNB_SENDERS, seen=False)
                for msg in mailbox.fetch(criteria, mark_seen=True):
                    try:
                        self._process_email(session, msg)
                    except Exception:
                        logger.exception("Failed to process email: %s", msg.subject)
                        self._log_email(session, msg, "error", error="Processing failed")
        except Exception:
            logger.exception("Failed to connect to IMAP server")
        finally:
            session.close()

    def _process_email(self, session: Session, msg: MailMessage) -> None:
        """Process a single Airbnb email."""
        # Check for duplicate
        existing = (
            session.query(EmailProcessingLog)
            .filter(EmailProcessingLog.message_id == (msg.uid or msg.date_str))
            .first()
        )
        if existing:
            return

        subject = msg.subject or ""
        body = msg.text or msg.html or ""

        # Classify the email
        email_type = self._classify_email(subject)

        if email_type == "booking_confirmation":
            self._handle_booking_confirmation(session, body, subject)
        elif email_type == "payout":
            self._handle_payout(session, body, subject)
        elif email_type == "cancellation":
            self._handle_cancellation(session, body, subject)
        else:
            email_type = "unknown"

        self._log_email(session, msg, email_type)

    def _classify_email(self, subject: str) -> str | None:
        """Classify email by subject line patterns."""
        for email_type, pattern in PATTERNS.items():
            if pattern.search(subject):
                return email_type
        return None

    def _handle_booking_confirmation(self, session: Session, body: str, subject: str) -> None:
        """Extract booking details from confirmation email."""
        confirmation_code = None
        guest_name = None
        checkin = None
        checkout = None

        match = CONFIRMATION_CODE_RE.search(body)
        if match:
            confirmation_code = match.group(1)

        match = GUEST_NAME_RE.search(body)
        if match:
            guest_name = match.group(1)

        match = CHECKIN_DATE_RE.search(body)
        if match:
            checkin = _try_parse_date(match.group(1))

        match = CHECKOUT_DATE_RE.search(body)
        if match:
            checkout = _try_parse_date(match.group(1))

        # Try to enrich existing booking by matching confirmation code or dates
        if confirmation_code:
            booking = (
                session.query(Booking)
                .filter(Booking.confirmation_code == confirmation_code)
                .first()
            )
            if not booking and checkin and checkout:
                # Match by dates
                booking = (
                    session.query(Booking)
                    .filter(
                        Booking.checkin_date == checkin,
                        Booking.checkout_date == checkout,
                        Booking.status == "confirmed",
                    )
                    .first()
                )

            if booking:
                if guest_name:
                    booking.guest_name = guest_name
                if confirmation_code:
                    booking.confirmation_code = confirmation_code
                session.commit()
                event_bus.publish(Event(
                    event_type=EventType.GUEST_INFO_ENRICHED,
                    data={"booking_id": booking.id, "guest_name": guest_name},
                ))
                logger.info("Enriched booking %s with guest info: %s", booking.id, guest_name)

    def _handle_payout(self, session: Session, body: str, subject: str) -> None:
        """Extract payout information from payout email."""
        amount = None
        confirmation_code = None

        match = PAYOUT_AMOUNT_RE.search(body)
        if match:
            amount = float(match.group(1).replace(",", ""))

        match = CONFIRMATION_CODE_RE.search(body)
        if match:
            confirmation_code = match.group(1)

        if amount:
            # Find associated booking
            booking_id = None
            property_id = None
            if confirmation_code:
                booking = (
                    session.query(Booking)
                    .filter(Booking.confirmation_code == confirmation_code)
                    .first()
                )
                if booking:
                    booking_id = booking.id
                    property_id = booking.property_id
                    booking.total_payout = amount

            payout = Payout(
                booking_id=booking_id,
                property_id=property_id,
                amount=amount,
                payout_date=date.today(),
                confirmation_code=confirmation_code,
                source="email",
            )
            session.add(payout)
            session.commit()
            event_bus.publish(Event(
                event_type=EventType.PAYOUT_RECEIVED,
                data={"payout_id": payout.id, "amount": amount},
            ))
            logger.info("Payout logged: $%.2f (code: %s)", amount, confirmation_code)

    def _handle_cancellation(self, session: Session, body: str, subject: str) -> None:
        """Handle cancellation email."""
        match = CONFIRMATION_CODE_RE.search(body)
        if match:
            code = match.group(1)
            booking = (
                session.query(Booking)
                .filter(Booking.confirmation_code == code)
                .first()
            )
            if booking:
                booking.status = "cancelled"
                session.commit()
                event_bus.publish(Event(
                    event_type=EventType.BOOKING_CANCELLED,
                    data={"booking_id": booking.id, "property_id": booking.property_id},
                ))
                logger.info("Booking %s cancelled via email", code)

    def _log_email(
        self, session: Session, msg: MailMessage, parsed_type: str, *, error: str | None = None
    ) -> None:
        """Log processed email for deduplication."""
        log_entry = EmailProcessingLog(
            message_id=msg.uid or msg.date_str or str(datetime.now(timezone.utc)),
            subject=msg.subject,
            sender=msg.from_,
            received_date=msg.date,
            parsed_type=parsed_type,
            status="error" if error else ("unrecognized" if parsed_type == "unknown" else "processed"),
            error_message=error,
        )
        session.add(log_entry)
        session.commit()
