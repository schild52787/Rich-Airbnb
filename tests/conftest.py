"""Shared test fixtures."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Set test environment before importing app modules
os.environ["DATABASE_URL"] = "sqlite://"  # In-memory DB for tests

from proppilot.database import Base
from proppilot.events import EventBus
from proppilot.models.booking import Booking
from proppilot.models.property import Property

# Import all models to register them
import proppilot.models.expense  # noqa: F401
import proppilot.models.message  # noqa: F401
import proppilot.models.payout  # noqa: F401
import proppilot.models.task  # noqa: F401


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def db_session():
    """Create a fresh in-memory database for each test."""
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def sample_property(db_session: Session) -> Property:
    """Create a sample property."""
    prop = Property(
        name="Test Loft",
        address="123 Test St",
        bedrooms=1,
        max_guests=4,
        base_price=120.0,
        cleaning_fee=75.0,
        wifi_password="test-wifi",
        lockbox_code="1234",
        checkout_time="11:00",
        checkin_time="15:00",
        cleaner_name="Test Cleaner",
        cleaner_phone="+15551234567",
    )
    db_session.add(prop)
    db_session.commit()
    return prop


@pytest.fixture
def sample_booking(db_session: Session, sample_property: Property) -> Booking:
    """Create a sample booking."""
    booking = Booking(
        property_id=sample_property.id,
        ical_uid="test-uid-123@airbnb.com",
        guest_name="John Doe",
        confirmation_code="HMXA1234AB",
        checkin_date=date(2026, 2, 1),
        checkout_date=date(2026, 2, 5),
        status="confirmed",
        source="ical",
    )
    db_session.add(booking)
    db_session.commit()
    return booking


@pytest.fixture
def event_bus():
    """Create a fresh event bus for each test."""
    return EventBus()


@pytest.fixture
def sample_ics() -> str:
    """Load sample iCal data."""
    return (FIXTURES_DIR / "sample.ics").read_text()
