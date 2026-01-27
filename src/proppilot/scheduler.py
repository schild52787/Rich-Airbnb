"""APScheduler setup for periodic tasks."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from proppilot.config import settings

logger = logging.getLogger(__name__)


def create_scheduler() -> BackgroundScheduler:
    """Create and configure the background scheduler."""
    from proppilot.modules.calendar_sync import CalendarSyncer
    from proppilot.modules.email_parser import AirbnbEmailParser
    from proppilot.modules.guest_comms import GuestCommunicator
    from proppilot.modules.operations import OperationsManager

    scheduler = BackgroundScheduler()
    sched_config = settings.get("scheduler", {})

    cal_syncer = CalendarSyncer()
    email_parser = AirbnbEmailParser()
    guest_comms = GuestCommunicator()
    ops_manager = OperationsManager()

    # Wire up event handlers
    guest_comms.setup_event_handlers()
    ops_manager.setup_event_handlers()

    # Calendar sync (every 15 min by default)
    scheduler.add_job(
        cal_syncer.sync_all,
        "interval",
        minutes=sched_config.get("calendar_sync_interval", 15),
        id="calendar_sync",
        name="Calendar Sync",
    )

    # Email check (every 3 min by default)
    if email_parser.is_configured:
        scheduler.add_job(
            email_parser.check_emails,
            "interval",
            minutes=sched_config.get("email_check_interval", 3),
            id="email_check",
            name="Email Check",
        )

    # Guest message scheduling check (every 5 min by default)
    scheduler.add_job(
        guest_comms.check_scheduled_messages,
        "interval",
        minutes=sched_config.get("message_check_interval", 5),
        id="message_check",
        name="Message Check",
    )

    # Send pending messages
    scheduler.add_job(
        guest_comms.send_pending_messages,
        "interval",
        minutes=sched_config.get("message_check_interval", 5),
        id="message_send",
        name="Message Send",
    )

    # Cleaner notifications (check every 30 min)
    scheduler.add_job(
        ops_manager.notify_cleaners,
        "interval",
        minutes=30,
        id="cleaner_notify",
        name="Cleaner Notifications",
    )

    # Morning reminders (run daily at 7 AM)
    scheduler.add_job(
        ops_manager.send_morning_reminders,
        "cron",
        hour=7,
        minute=0,
        id="morning_reminders",
        name="Morning Reminders",
    )

    logger.info("Scheduler configured with %d jobs", len(scheduler.get_jobs()))
    return scheduler
