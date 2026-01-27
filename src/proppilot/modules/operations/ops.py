"""Cleaning task automation, maintenance CRUD, and inventory management."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from proppilot.config import get_env, settings
from proppilot.database import get_session
from proppilot.events import Event, EventType, event_bus
from proppilot.models.booking import Booking
from proppilot.models.property import Property
from proppilot.models.task import CleaningTask, InventoryItem, MaintenanceTask

logger = logging.getLogger(__name__)


class OperationsManager:
    """Manages cleaning tasks, maintenance, and inventory."""

    def __init__(self) -> None:
        self._twilio_client = None

    def setup_event_handlers(self) -> None:
        """Subscribe to booking events for auto-creating cleaning tasks."""
        event_bus.subscribe(EventType.BOOKING_NEW, self._on_new_booking)
        event_bus.subscribe(EventType.BOOKING_CANCELLED, self._on_booking_cancelled)

    def _on_new_booking(self, event: Event) -> None:
        """Auto-create cleaning task when a new booking arrives."""
        booking_id = event.data.get("booking_id")
        property_id = event.data.get("property_id")
        if booking_id and property_id:
            self.create_cleaning_task(booking_id, property_id)

    def _on_booking_cancelled(self, event: Event) -> None:
        """Cancel associated cleaning task when booking is cancelled."""
        booking_id = event.data.get("booking_id")
        if not booking_id:
            return
        session = get_session()
        try:
            tasks = (
                session.query(CleaningTask)
                .filter(
                    CleaningTask.booking_id == booking_id,
                    CleaningTask.status.in_(["pending", "notified"]),
                )
                .all()
            )
            for task in tasks:
                task.status = "cancelled"
            session.commit()
            logger.info("Cancelled %d cleaning tasks for booking %s", len(tasks), booking_id)
        finally:
            session.close()

    def create_cleaning_task(self, booking_id: int, property_id: int) -> CleaningTask | None:
        """Create a cleaning task for a booking's checkout date."""
        session = get_session()
        try:
            booking = session.query(Booking).get(booking_id)
            if not booking:
                return None

            # Check for duplicate
            existing = (
                session.query(CleaningTask)
                .filter(
                    CleaningTask.booking_id == booking_id,
                    CleaningTask.status != "cancelled",
                )
                .first()
            )
            if existing:
                return existing

            # Check if same-day turnover
            is_turnover = self._check_same_day_turnover(session, property_id, booking.checkout_date)

            task = CleaningTask(
                property_id=property_id,
                booking_id=booking_id,
                scheduled_date=booking.checkout_date,
                status="pending",
                is_turnover=is_turnover,
                priority="high" if is_turnover else "normal",
            )
            session.add(task)
            session.commit()

            logger.info(
                "Created cleaning task for %s on %s (turnover: %s)",
                booking.checkout_date,
                property_id,
                is_turnover,
            )
            event_bus.publish(Event(
                event_type=EventType.CLEANING_TASK_CREATED,
                data={
                    "task_id": task.id,
                    "property_id": property_id,
                    "date": str(booking.checkout_date),
                    "is_turnover": is_turnover,
                },
            ))
            return task
        finally:
            session.close()

    def _check_same_day_turnover(self, session: Session, property_id: int, checkout_date: date) -> bool:
        """Check if another booking checks in on the same day (turnover)."""
        return (
            session.query(Booking)
            .filter(
                Booking.property_id == property_id,
                Booking.checkin_date == checkout_date,
                Booking.status == "confirmed",
            )
            .first()
        ) is not None

    def notify_cleaners(self) -> None:
        """Send SMS/email notifications to cleaners for upcoming tasks."""
        session = get_session()
        try:
            today = date.today()
            # Find tasks that need notification (tomorrow or today, not yet notified)
            tasks = (
                session.query(CleaningTask)
                .filter(
                    CleaningTask.status == "pending",
                    CleaningTask.cleaner_notified.is_(False),
                    CleaningTask.scheduled_date <= today,
                )
                .all()
            )

            for task in tasks:
                prop = session.query(Property).get(task.property_id)
                if not prop or not prop.cleaner_phone:
                    continue

                message = self._format_cleaner_notification(task, prop)
                success = self._send_sms(prop.cleaner_phone, message)

                if success:
                    task.cleaner_notified = True
                    task.cleaner_notified_at = datetime.now(timezone.utc)
                    task.status = "notified"
                    session.commit()
                    logger.info("Notified cleaner for task %s", task.id)
        finally:
            session.close()

    def send_morning_reminders(self) -> None:
        """Send morning-of reminders for today's cleaning tasks."""
        session = get_session()
        try:
            today = date.today()
            tasks = (
                session.query(CleaningTask)
                .filter(
                    CleaningTask.scheduled_date == today,
                    CleaningTask.status.in_(["pending", "notified"]),
                )
                .all()
            )
            for task in tasks:
                prop = session.query(Property).get(task.property_id)
                if not prop or not prop.cleaner_phone:
                    continue

                priority = "URGENT TURNOVER - " if task.is_turnover else ""
                message = (
                    f"{priority}Reminder: Cleaning today at {prop.name}, "
                    f"{prop.address}. Checkout time: {prop.checkout_time}."
                )
                self._send_sms(prop.cleaner_phone, message)
        finally:
            session.close()

    def _format_cleaner_notification(self, task: CleaningTask, prop: Property) -> str:
        """Format SMS message for cleaner."""
        priority = "SAME-DAY TURNOVER - " if task.is_turnover else ""
        return (
            f"{priority}New cleaning task:\n"
            f"Property: {prop.name}\n"
            f"Address: {prop.address}\n"
            f"Date: {task.scheduled_date.strftime('%A, %B %d')}\n"
            f"Checkout: {prop.checkout_time}\n"
            f"Notes: {task.notes or 'Standard cleaning'}"
        )

    def _send_sms(self, to_number: str, message: str) -> bool:
        """Send SMS via Twilio."""
        account_sid = get_env("TWILIO_ACCOUNT_SID")
        auth_token = get_env("TWILIO_AUTH_TOKEN")
        from_number = get_env("TWILIO_FROM_NUMBER")

        if not all([account_sid, auth_token, from_number]):
            logger.warning("Twilio not configured, SMS not sent")
            return False

        try:
            if self._twilio_client is None:
                from twilio.rest import Client

                self._twilio_client = Client(account_sid, auth_token)

            self._twilio_client.messages.create(
                body=message,
                from_=from_number,
                to=to_number,
            )
            logger.info("SMS sent to %s", to_number)
            return True
        except Exception:
            logger.exception("Failed to send SMS to %s", to_number)
            return False

    # --- Maintenance CRUD ---

    def create_maintenance_task(
        self,
        property_id: int,
        title: str,
        description: str | None = None,
        priority: str = "normal",
        cost: float | None = None,
        due_date: date | None = None,
    ) -> MaintenanceTask:
        session = get_session()
        try:
            task = MaintenanceTask(
                property_id=property_id,
                title=title,
                description=description,
                priority=priority,
                cost=cost,
                due_date=due_date,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            return task
        finally:
            session.close()

    def complete_maintenance_task(self, task_id: int, cost: float | None = None) -> None:
        session = get_session()
        try:
            task = session.query(MaintenanceTask).get(task_id)
            if task:
                task.status = "completed"
                task.completed_at = datetime.now(timezone.utc)
                if cost is not None:
                    task.cost = cost
                session.commit()
        finally:
            session.close()

    # --- Inventory ---

    def check_inventory_alerts(self) -> list[InventoryItem]:
        """Return inventory items that need reordering."""
        session = get_session()
        try:
            items = session.query(InventoryItem).all()
            return [item for item in items if item.needs_reorder]
        finally:
            session.close()

    def update_inventory(self, item_id: int, quantity: int) -> None:
        session = get_session()
        try:
            item = session.query(InventoryItem).get(item_id)
            if item:
                item.quantity = quantity
                session.commit()
        finally:
            session.close()
