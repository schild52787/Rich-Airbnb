"""SQLAlchemy engine and session setup."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from proppilot.config import get_database_url


class Base(DeclarativeBase):
    pass


engine = create_engine(
    get_database_url(),
    echo=False,
    connect_args={"check_same_thread": False},  # SQLite needs this for multi-thread
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Session:
    """Create a new database session."""
    return SessionLocal()


def init_db() -> None:
    """Create all tables. Import models first so they register with Base."""
    # Import all models to ensure they are registered
    import proppilot.models.booking  # noqa: F401
    import proppilot.models.expense  # noqa: F401
    import proppilot.models.message  # noqa: F401
    import proppilot.models.payout  # noqa: F401
    import proppilot.models.property  # noqa: F401
    import proppilot.models.task  # noqa: F401

    Base.metadata.create_all(bind=engine)
