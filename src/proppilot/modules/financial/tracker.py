"""Income/expense tracking, reports, and export."""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from proppilot.database import get_session
from proppilot.models.expense import SCHEDULE_E_CATEGORIES, Expense
from proppilot.models.payout import Payout
from proppilot.models.property import Property

logger = logging.getLogger(__name__)


@dataclass
class MonthlyReport:
    property_id: int
    property_name: str
    year: int
    month: int
    total_income: float
    total_expenses: float
    net_income: float
    expenses_by_category: dict[str, float] = field(default_factory=dict)
    num_payouts: int = 0


@dataclass
class AnnualReport:
    property_id: int
    property_name: str
    year: int
    total_income: float
    total_expenses: float
    net_income: float
    expenses_by_category: dict[str, float] = field(default_factory=dict)
    monthly_breakdown: list[MonthlyReport] = field(default_factory=list)


class FinancialTracker:
    """Tracks income and expenses with reporting and export."""

    def add_expense(
        self,
        property_id: int,
        category: str,
        description: str,
        amount: float,
        expense_date: date,
        vendor: str | None = None,
        is_recurring: bool = False,
        recurrence_months: int | None = None,
        notes: str | None = None,
    ) -> Expense:
        """Add a new expense."""
        if category not in SCHEDULE_E_CATEGORIES:
            raise ValueError(f"Invalid category: {category}. Must be one of {SCHEDULE_E_CATEGORIES}")

        session = get_session()
        try:
            expense = Expense(
                property_id=property_id,
                category=category,
                description=description,
                amount=amount,
                date=expense_date,
                vendor=vendor,
                is_recurring=is_recurring,
                recurrence_months=recurrence_months,
                notes=notes,
            )
            session.add(expense)
            session.commit()
            session.refresh(expense)
            logger.info("Added expense: %s $%.2f for property %s", category, amount, property_id)
            return expense
        finally:
            session.close()

    def add_manual_payout(
        self,
        property_id: int,
        amount: float,
        payout_date: date,
        booking_id: int | None = None,
        confirmation_code: str | None = None,
        notes: str | None = None,
    ) -> Payout:
        """Manually add a payout."""
        session = get_session()
        try:
            payout = Payout(
                booking_id=booking_id,
                property_id=property_id,
                amount=amount,
                payout_date=payout_date,
                confirmation_code=confirmation_code,
                source="manual",
                notes=notes,
            )
            session.add(payout)
            session.commit()
            session.refresh(payout)
            return payout
        finally:
            session.close()

    def get_monthly_report(self, property_id: int, year: int, month: int) -> MonthlyReport:
        """Generate a monthly financial report for a property."""
        session = get_session()
        try:
            prop = session.query(Property).get(property_id)
            prop_name = prop.name if prop else f"Property {property_id}"

            # Income
            income_result = (
                session.query(func.sum(Payout.amount), func.count(Payout.id))
                .filter(
                    Payout.property_id == property_id,
                    extract("year", Payout.payout_date) == year,
                    extract("month", Payout.payout_date) == month,
                )
                .first()
            )
            total_income = income_result[0] or 0.0
            num_payouts = income_result[1] or 0

            # Expenses by category
            expense_rows = (
                session.query(Expense.category, func.sum(Expense.amount))
                .filter(
                    Expense.property_id == property_id,
                    extract("year", Expense.date) == year,
                    extract("month", Expense.date) == month,
                )
                .group_by(Expense.category)
                .all()
            )
            expenses_by_category = {row[0]: row[1] for row in expense_rows}
            total_expenses = sum(expenses_by_category.values())

            return MonthlyReport(
                property_id=property_id,
                property_name=prop_name,
                year=year,
                month=month,
                total_income=total_income,
                total_expenses=total_expenses,
                net_income=total_income - total_expenses,
                expenses_by_category=expenses_by_category,
                num_payouts=num_payouts,
            )
        finally:
            session.close()

    def get_annual_report(self, property_id: int, year: int) -> AnnualReport:
        """Generate an annual financial report with monthly breakdown."""
        monthly_reports = []
        for month in range(1, 13):
            monthly_reports.append(self.get_monthly_report(property_id, year, month))

        total_income = sum(r.total_income for r in monthly_reports)
        total_expenses = sum(r.total_expenses for r in monthly_reports)

        # Aggregate expenses by category
        all_categories: dict[str, float] = {}
        for report in monthly_reports:
            for cat, amount in report.expenses_by_category.items():
                all_categories[cat] = all_categories.get(cat, 0) + amount

        prop_name = monthly_reports[0].property_name if monthly_reports else f"Property {property_id}"

        return AnnualReport(
            property_id=property_id,
            property_name=prop_name,
            year=year,
            total_income=total_income,
            total_expenses=total_expenses,
            net_income=total_income - total_expenses,
            expenses_by_category=all_categories,
            monthly_breakdown=monthly_reports,
        )

    def export_expenses_csv(self, property_id: int, year: int) -> str:
        """Export expenses to CSV string."""
        session = get_session()
        try:
            expenses = (
                session.query(Expense)
                .filter(
                    Expense.property_id == property_id,
                    extract("year", Expense.date) == year,
                )
                .order_by(Expense.date)
                .all()
            )

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Date", "Category", "Description", "Amount", "Vendor", "Recurring", "Notes",
            ])
            for exp in expenses:
                writer.writerow([
                    exp.date.isoformat(),
                    exp.category,
                    exp.description,
                    f"{exp.amount:.2f}",
                    exp.vendor or "",
                    "Yes" if exp.is_recurring else "No",
                    exp.notes or "",
                ])
            return output.getvalue()
        finally:
            session.close()

    def export_income_csv(self, property_id: int, year: int) -> str:
        """Export income/payouts to CSV string."""
        session = get_session()
        try:
            payouts = (
                session.query(Payout)
                .filter(
                    Payout.property_id == property_id,
                    extract("year", Payout.payout_date) == year,
                )
                .order_by(Payout.payout_date)
                .all()
            )

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Date", "Amount", "Confirmation Code", "Source", "Notes",
            ])
            for p in payouts:
                writer.writerow([
                    p.payout_date.isoformat(),
                    f"{p.amount:.2f}",
                    p.confirmation_code or "",
                    p.source,
                    p.notes or "",
                ])
            return output.getvalue()
        finally:
            session.close()

    def export_schedule_e_summary(self, property_id: int, year: int) -> dict[str, float]:
        """Generate IRS Schedule E summary for tax preparation."""
        report = self.get_annual_report(property_id, year)
        summary: dict[str, float] = {"gross_rental_income": report.total_income}

        # Map to Schedule E line items
        for category in SCHEDULE_E_CATEGORIES:
            summary[category] = report.expenses_by_category.get(category, 0.0)

        summary["total_expenses"] = report.total_expenses
        summary["net_rental_income"] = report.net_income
        return summary
