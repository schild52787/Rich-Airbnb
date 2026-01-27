"""Tests for the event bus."""

from proppilot.events import Event, EventBus, EventType


def test_subscribe_and_publish():
    bus = EventBus()
    received = []

    def handler(event: Event):
        received.append(event)

    bus.subscribe(EventType.BOOKING_NEW, handler)
    bus.publish(Event(event_type=EventType.BOOKING_NEW, data={"booking_id": 1}))

    assert len(received) == 1
    assert received[0].data["booking_id"] == 1


def test_no_cross_event_delivery():
    bus = EventBus()
    received = []

    def handler(event: Event):
        received.append(event)

    bus.subscribe(EventType.BOOKING_NEW, handler)
    bus.publish(Event(event_type=EventType.BOOKING_CANCELLED, data={}))

    assert len(received) == 0


def test_multiple_subscribers():
    bus = EventBus()
    calls = {"a": 0, "b": 0}

    def handler_a(event: Event):
        calls["a"] += 1

    def handler_b(event: Event):
        calls["b"] += 1

    bus.subscribe(EventType.PAYOUT_RECEIVED, handler_a)
    bus.subscribe(EventType.PAYOUT_RECEIVED, handler_b)
    bus.publish(Event(event_type=EventType.PAYOUT_RECEIVED, data={"amount": 100}))

    assert calls["a"] == 1
    assert calls["b"] == 1


def test_subscriber_error_does_not_stop_others():
    bus = EventBus()
    calls = []

    def bad_handler(event: Event):
        raise ValueError("boom")

    def good_handler(event: Event):
        calls.append(True)

    bus.subscribe(EventType.BOOKING_NEW, bad_handler)
    bus.subscribe(EventType.BOOKING_NEW, good_handler)
    bus.publish(Event(event_type=EventType.BOOKING_NEW, data={}))

    assert len(calls) == 1
