"""Guest communication - template rendering, message scheduling, and delivery."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from proppilot.config import get_env, settings
from proppilot.database import get_session
from proppilot.events import Event, EventType, event_bus
from proppilot.models.booking import Booking
from proppilot.models.message import MessageLog, MessageTemplate
from proppilot.models.property import Property

logger = logging.getLogger(__name__)

# Locate template directory
TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "templates"


class GuestCommunicator:
    """Manages guest message templates, scheduling, and delivery."""

    def __init__(self) -> None:
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(default=False),
        )

    def setup_event_handlers(self) -> None:
        """Subscribe to events for automatic message triggering."""
        event_bus.subscribe(EventType.BOOKING_NEW, self._on_new_booking)

    def _on_new_booking(self, event: Event) -> None:
        """Queue a welcome message when a new booking is detected."""
        booking_id = event.data.get("booking_id")
        if booking_id:
            self.queue_message(booking_id, "welcome")

    def queue_message(
        self,
        booking_id: int,
        template_name: str,
        *,
        channel: str = "airbnb",
        scheduled_at: datetime | None = None,
    ) -> MessageLog | None:
        """Render a template and queue it for delivery."""
        session = get_session()
        try:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                logger.warning("Booking %s not found, skipping message", booking_id)
                return None

            prop = session.query(Property).get(booking.property_id)
            if not prop:
                return None

            # Check for duplicate
            existing = (
                session.query(MessageLog)
                .filter(
                    MessageLog.booking_id == booking_id,
                    MessageLog.template_name == template_name,
                    MessageLog.status.in_(["queued", "sent", "copied"]),
                )
                .first()
            )
            if existing:
                logger.debug("Message %s already queued for booking %s", template_name, booking_id)
                return existing

            body = self._render_template(template_name, booking, prop)
            if not body:
                return None

            msg = MessageLog(
                booking_id=booking_id,
                template_name=template_name,
                channel=channel,
                recipient=booking.guest_name or "Guest",
                subject=f"{template_name.replace('_', ' ').title()} - {prop.name}",
                body=body,
                status="queued",
                scheduled_at=scheduled_at or datetime.now(timezone.utc),
            )
            session.add(msg)
            session.commit()
            logger.info("Queued %s message for booking %s", template_name, booking_id)

            event_bus.publish(Event(
                event_type=EventType.MESSAGE_QUEUED,
                data={"message_id": msg.id, "template": template_name},
            ))
            return msg
        finally:
            session.close()

    def check_scheduled_messages(self) -> None:
        """Check for bookings that need scheduled messages (check-in, checkout, review)."""
        session = get_session()
        try:
            now = datetime.now(timezone.utc)
            today = now.date()
            msg_config = settings.get("messages", {})

            bookings = (
                session.query(Booking)
                .filter(Booking.status == "confirmed")
                .all()
            )

            for booking in bookings:
                # Check-in instructions
                hours_before = msg_config.get("check_in_instructions", {}).get(
                    "trigger_hours_before_checkin", 24
                )
                checkin_dt = datetime.combine(booking.checkin_date, datetime.min.time()).replace(
                    tzinfo=timezone.utc
                )
                if timedelta(0) <= (checkin_dt - now) <= timedelta(hours=hours_before):
                    self.queue_message(booking.id, "check_in_instructions")

                # Checkout reminder
                hours_before = msg_config.get("checkout_reminder", {}).get(
                    "trigger_hours_before_checkout", 18
                )
                checkout_dt = datetime.combine(booking.checkout_date, datetime.min.time()).replace(
                    tzinfo=timezone.utc
                )
                if timedelta(0) <= (checkout_dt - now) <= timedelta(hours=hours_before):
                    self.queue_message(booking.id, "checkout_reminder")

                # Review request
                hours_after = msg_config.get("review_request", {}).get(
                    "trigger_hours_after_checkout", 48
                )
                if timedelta(0) <= (now - checkout_dt) <= timedelta(hours=hours_after):
                    self.queue_message(booking.id, "review_request")
        finally:
            session.close()

    def send_pending_messages(self) -> None:
        """Attempt to send messages that are queued and due."""
        session = get_session()
        try:
            now = datetime.now(timezone.utc)
            messages = (
                session.query(MessageLog)
                .filter(
                    MessageLog.status == "queued",
                    MessageLog.scheduled_at <= now,
                )
                .all()
            )
            for msg in messages:
                if msg.channel == "email" and msg.booking:
                    self._send_email(msg)
                    msg.status = "sent"
                    msg.sent_at = now
                elif msg.channel == "airbnb":
                    # Airbnb messages stay "queued" for host to copy-paste
                    pass
                session.commit()
        finally:
            session.close()

    def _render_template(self, template_name: str, booking: Booking, prop: Property) -> str | None:
        """Render a Jinja2 message template."""
        filename = f"{template_name}.txt"
        try:
            template = self._jinja_env.get_template(filename)
        except Exception:
            logger.warning("Template not found: %s", filename)
            # Fall back to DB template
            session = get_session()
            try:
                db_template = (
                    session.query(MessageTemplate)
                    .filter(MessageTemplate.name == template_name, MessageTemplate.is_active.is_(True))
                    .first()
                )
                if db_template:
                    from jinja2 import Template

                    template = Template(db_template.body)
                else:
                    logger.error("No template found for %s", template_name)
                    return None
            finally:
                session.close()

        context = {
            "guest_name": booking.guest_name or "Guest",
            "property_name": prop.name,
            "address": prop.address,
            "checkin_date": booking.checkin_date.strftime("%B %d, %Y"),
            "checkout_date": booking.checkout_date.strftime("%B %d, %Y"),
            "checkin_time": prop.checkin_time,
            "checkout_time": prop.checkout_time,
            "wifi_password": prop.wifi_password or "N/A",
            "lockbox_code": prop.lockbox_code or "N/A",
            "nights": booking.nights,
            "num_guests": booking.num_guests or "",
            "notes": prop.notes or "",
            "confirmation_code": booking.confirmation_code or "",
        }
        return template.render(**context)

    def _send_email(self, msg: MessageLog) -> None:
        """Send a message via SMTP email."""
        smtp_host = get_env("SMTP_HOST")
        smtp_port = int(get_env("SMTP_PORT", "587"))
        smtp_user = get_env("SMTP_USER")
        smtp_password = get_env("SMTP_PASSWORD")

        if not all([smtp_host, smtp_user, smtp_password]):
            logger.warning("SMTP not configured, cannot send email")
            return

        booking = msg.booking
        if not booking or not booking.guest_email:
            logger.warning("No guest email for message %s", msg.id)
            return

        email_msg = MIMEText(msg.body)
        email_msg["Subject"] = msg.subject or "Message from your host"
        email_msg["From"] = smtp_user
        email_msg["To"] = booking.guest_email

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(email_msg)
            logger.info("Email sent to %s", booking.guest_email)
        except Exception:
            logger.exception("Failed to send email to %s", booking.guest_email)
            raise
