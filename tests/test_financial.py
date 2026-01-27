"""Tests for financial tracking."""

from datetime import date

from sqlalchemy.orm import Session

from proppilot.models.expense import Expense
from proppilot.models.payout import Payout
from proppilot.models.property import Property


def test_monthly_income_sum(db_session: Session, sample_property: Property):
    """Test that payouts sum correctly for a month."""
    for i, amount in enumerate([480.0, 320.0, 550.0]):
        payout = Payout(
            property_id=sample_property.id,
            amount=amount,
            payout_date=date(2026, 2, 5 + i),
            source="manual",
        )
        db_session.add(payout)
    db_session.commit()

    from sqlalchemy import extract, func
    total = (
        db_session.query(func.sum(Payout.amount))
        .filter(
            Payout.property_id == sample_property.id,
            extract("year", Payout.payout_date) == 2026,
            extract("month", Payout.payout_date) == 2,
        )
        .scalar()
    )
    assert total == 1350.0


def test_expense_by_category(db_session: Session, sample_property: Property):
    """Test expense categorization."""
    expenses = [
        Expense(property_id=sample_property.id, category="cleaning_and_maintenance",
                description="Cleaning", amount=100, date=date(2026, 2, 1)),
        Expense(property_id=sample_property.id, category="cleaning_and_maintenance",
                description="Supplies", amount=50, date=date(2026, 2, 15)),
        Expense(property_id=sample_property.id, category="insurance",
                description="Liability", amount=200, date=date(2026, 2, 1)),
    ]
    for e in expenses:
        db_session.add(e)
    db_session.commit()

    from sqlalchemy import extract, func
    results = (
        db_session.query(Expense.category, func.sum(Expense.amount))
        .filter(
            Expense.property_id == sample_property.id,
            extract("year", Expense.date) == 2026,
            extract("month", Expense.date) == 2,
        )
        .group_by(Expense.category)
        .all()
    )
    by_cat = {r[0]: r[1] for r in results}
    assert by_cat["cleaning_and_maintenance"] == 150.0
    assert by_cat["insurance"] == 200.0
