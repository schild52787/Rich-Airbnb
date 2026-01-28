"""Smoke tests for FastAPI app routes."""

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import proppilot.database as db_module
from proppilot.database import Base

# Import all models so Base.metadata knows about them
import proppilot.models.booking  # noqa: F401
import proppilot.models.expense  # noqa: F401
import proppilot.models.message  # noqa: F401
import proppilot.models.payout  # noqa: F401
import proppilot.models.property  # noqa: F401
import proppilot.models.task  # noqa: F401

from proppilot.models.property import Property


@pytest.fixture
def app_client(tmp_path):
    """Create a test client with a temp SQLite DB and no scheduler."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    test_engine = create_engine(
        db_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, expire_on_commit=False)

    # Seed a property
    session = TestSession()
    prop = Property(name="Test Property", address="123 Test St", base_price=100.0)
    session.add(prop)
    session.commit()
    session.close()

    # Save originals and swap
    orig_engine = db_module.engine
    orig_session = db_module.SessionLocal
    orig_get_session = db_module.get_session
    db_module.engine = test_engine
    db_module.SessionLocal = TestSession
    db_module.get_session = lambda: TestSession()

    mock_scheduler = MagicMock()
    mock_scheduler.start = MagicMock()
    mock_scheduler.shutdown = MagicMock()
    mock_scheduler.get_jobs = MagicMock(return_value=[])

    # Also patch the import in app.py since it captured the old reference
    with (
        patch("proppilot.app.get_session", side_effect=lambda: TestSession()),
        patch("proppilot.app.create_scheduler", return_value=mock_scheduler),
        patch("proppilot.app.seed_properties_from_config"),
        patch("proppilot.app.seed_message_templates"),
        patch("proppilot.app.init_db"),
    ):
        from proppilot.app import app
        client = TestClient(app)
        yield client

    db_module.engine = orig_engine
    db_module.SessionLocal = orig_session
    db_module.get_session = orig_get_session
    test_engine.dispose()


def test_dashboard_home(app_client):
    """Dashboard home page returns 200."""
    response = app_client.get("/")
    assert response.status_code == 200
    assert "PropPilot" in response.text


def test_bookings_page(app_client):
    """Bookings page returns 200."""
    response = app_client.get("/bookings")
    assert response.status_code == 200


def test_cleaning_page(app_client):
    """Cleaning page returns 200."""
    response = app_client.get("/cleaning")
    assert response.status_code == 200


def test_messages_page(app_client):
    """Messages page returns 200."""
    response = app_client.get("/messages")
    assert response.status_code == 200


def test_maintenance_page(app_client):
    """Maintenance page returns 200."""
    response = app_client.get("/maintenance")
    assert response.status_code == 200


def test_inventory_page(app_client):
    """Inventory page returns 200."""
    response = app_client.get("/inventory")
    assert response.status_code == 200
