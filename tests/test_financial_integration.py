"""Integration tests for FinancialTracker — reports, CSV export, Schedule E."""

from datetime import date
from unittest.mock import patch

from sqlalchemy.orm import Session

from proppilot.models.expense import Expense
from proppilot.models.payout import Payout
from proppilot.models.property import Property
from proppilot.modules.financial.tracker import FinancialTracker


def _noop_close(self):
    pass


def _seed_financial_data(db_session: Session, prop: Property):
    """Seed payouts and expenses for Feb 2026."""
    payouts = [
        Payout(property_id=prop.id, amount=480.0, payout_date=date(2026, 2, 5), source="email"),
        Payout(property_id=prop.id, amount=320.0, payout_date=date(2026, 2, 12), source="manual"),
    ]
    expenses = [
        Expense(property_id=prop.id, category="cleaning_and_maintenance",
                description="Regular clean", amount=100.0, date=date(2026, 2, 6)),
        Expense(property_id=prop.id, category="supplies",
                description="Towels", amount=45.0, date=date(2026, 2, 10)),
        Expense(property_id=prop.id, category="utilities",
                description="Electric", amount=80.0, date=date(2026, 2, 15)),
    ]
    for obj in payouts + expenses:
        db_session.add(obj)
    db_session.commit()


def test_monthly_report(db_session: Session, sample_property: Property):
    """Monthly report sums income and categorizes expenses."""
    _seed_financial_data(db_session, sample_property)

    with (
        patch("proppilot.modules.financial.tracker.get_session", return_value=db_session),
        patch.object(type(db_session), "close", _noop_close),
    ):
        tracker = FinancialTracker()
        report = tracker.get_monthly_report(sample_property.id, 2026, 2)

    assert report.total_income == 800.0
    assert report.num_payouts == 2
    assert report.total_expenses == 225.0
    assert report.net_income == 575.0
    assert report.expenses_by_category["cleaning_and_maintenance"] == 100.0
    assert report.expenses_by_category["supplies"] == 45.0
    assert report.expenses_by_category["utilities"] == 80.0


def test_annual_report(db_session: Session, sample_property: Property):
    """Annual report aggregates all months."""
    _seed_financial_data(db_session, sample_property)

    with (
        patch("proppilot.modules.financial.tracker.get_session", return_value=db_session),
        patch.object(type(db_session), "close", _noop_close),
    ):
        tracker = FinancialTracker()
        report = tracker.get_annual_report(sample_property.id, 2026)

    assert report.total_income == 800.0
    assert report.total_expenses == 225.0
    assert report.net_income == 575.0
    assert len(report.monthly_breakdown) == 12
    # Only February should have data
    feb = report.monthly_breakdown[1]  # 0-indexed, month 2 is index 1
    assert feb.total_income == 800.0
    assert feb.total_expenses == 225.0


def test_add_expense_validates_category(db_session: Session, sample_property: Property):
    """Adding expense with invalid category raises ValueError."""
    import pytest

    with (
        patch("proppilot.modules.financial.tracker.get_session", return_value=db_session),
        patch.object(type(db_session), "close", _noop_close),
    ):
        tracker = FinancialTracker()
        with pytest.raises(ValueError, match="Invalid category"):
            tracker.add_expense(sample_property.id, "nonexistent", "test", 100, date(2026, 2, 1))


def test_add_manual_payout(db_session: Session, sample_property: Property):
    """Manual payout is created with correct fields."""
    with (
        patch("proppilot.modules.financial.tracker.get_session", return_value=db_session),
        patch.object(type(db_session), "close", _noop_close),
    ):
        tracker = FinancialTracker()
        payout = tracker.add_manual_payout(
            property_id=sample_property.id,
            amount=500.0,
            payout_date=date(2026, 3, 1),
            confirmation_code="MANUAL123",
            notes="Test payout",
        )

    assert payout.amount == 500.0
    assert payout.source == "manual"
    assert payout.confirmation_code == "MANUAL123"


def test_export_expenses_csv(db_session: Session, sample_property: Property):
    """CSV export includes all expenses with correct format."""
    _seed_financial_data(db_session, sample_property)

    with (
        patch("proppilot.modules.financial.tracker.get_session", return_value=db_session),
        patch.object(type(db_session), "close", _noop_close),
    ):
        tracker = FinancialTracker()
        csv_output = tracker.export_expenses_csv(sample_property.id, 2026)

    lines = [l.strip() for l in csv_output.strip().splitlines()]
    assert lines[0] == "Date,Category,Description,Amount,Vendor,Recurring,Notes"
    assert len(lines) == 4  # Header + 3 expenses
    assert "cleaning_and_maintenance" in lines[1]
    assert "100.00" in lines[1]


def test_export_income_csv(db_session: Session, sample_property: Property):
    """Income CSV export includes all payouts."""
    _seed_financial_data(db_session, sample_property)

    with (
        patch("proppilot.modules.financial.tracker.get_session", return_value=db_session),
        patch.object(type(db_session), "close", _noop_close),
    ):
        tracker = FinancialTracker()
        csv_output = tracker.export_income_csv(sample_property.id, 2026)

    lines = [l.strip() for l in csv_output.strip().splitlines()]
    assert lines[0] == "Date,Amount,Confirmation Code,Source,Notes"
    assert len(lines) == 3  # Header + 2 payouts


def test_schedule_e_summary(db_session: Session, sample_property: Property):
    """Schedule E summary maps to IRS categories."""
    _seed_financial_data(db_session, sample_property)

    with (
        patch("proppilot.modules.financial.tracker.get_session", return_value=db_session),
        patch.object(type(db_session), "close", _noop_close),
    ):
        tracker = FinancialTracker()
        summary = tracker.export_schedule_e_summary(sample_property.id, 2026)

    assert summary["gross_rental_income"] == 800.0
    assert summary["total_expenses"] == 225.0
    assert summary["net_rental_income"] == 575.0
    assert summary["cleaning_and_maintenance"] == 100.0
    assert summary["supplies"] == 45.0
    assert summary["mortgage_interest"] == 0.0  # Not seeded
