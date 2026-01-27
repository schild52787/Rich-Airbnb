"""Lightweight in-process pub/sub event bus."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    BOOKING_NEW = "booking_new"
    BOOKING_MODIFIED = "booking_modified"
    BOOKING_CANCELLED = "booking_cancelled"
    PAYOUT_RECEIVED = "payout_received"
    GUEST_INFO_ENRICHED = "guest_info_enriched"
    CLEANING_TASK_CREATED = "cleaning_task_created"
    MESSAGE_QUEUED = "message_queued"
    PRICE_RECOMMENDATION = "price_recommendation"


@dataclass
class Event:
    event_type: EventType
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Type for subscriber callbacks
Subscriber = Callable[[Event], None]


class EventBus:
    """Simple synchronous pub/sub event bus."""

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Subscriber]] = defaultdict(list)

    def subscribe(self, event_type: EventType, callback: Subscriber) -> None:
        """Register a callback for an event type."""
        self._subscribers[event_type].append(callback)
        logger.debug("Subscribed %s to %s", callback.__name__, event_type.value)

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        logger.info("Publishing event: %s", event.event_type.value)
        for callback in self._subscribers.get(event.event_type, []):
            try:
                callback(event)
            except Exception:
                logger.exception(
                    "Error in subscriber %s for event %s",
                    callback.__name__,
                    event.event_type.value,
                )


# Global event bus instance
event_bus = EventBus()
