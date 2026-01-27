"""FastAPI application with dashboard and API routes."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from proppilot.config import settings
from proppilot.database import get_session, init_db
from proppilot.models.booking import Booking
from proppilot.models.expense import SCHEDULE_E_CATEGORIES, Expense
from proppilot.models.message import MessageLog, MessageTemplate
from proppilot.models.payout import Payout
from proppilot.models.property import Property
from proppilot.models.task import CleaningTask, InventoryItem, MaintenanceTask
from proppilot.modules.calendar_sync import CalendarSyncer
from proppilot.modules.financial import FinancialTracker
from proppilot.modules.operations import OperationsManager
from proppilot.modules.pricing import PricingEngine
from proppilot.scheduler import create_scheduler

logger = logging.getLogger(__name__)

DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
TEMPLATES_DIR = DASHBOARD_DIR / "templates"
STATIC_DIR = DASHBOARD_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Starting PropPilot...")
    init_db()
    seed_properties_from_config()
    seed_message_templates()

    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started.")

    yield

    scheduler.shutdown()
    logger.info("PropPilot shut down.")


app = FastAPI(title="PropPilot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def seed_properties_from_config() -> None:
    """Seed properties from config.yaml if not already in DB."""
    session = get_session()
    try:
        for prop_cfg in settings.get("properties", []):
            existing = (
                session.query(Property).filter(Property.name == prop_cfg["name"]).first()
            )
            if existing:
                # Update iCal URL if changed
                if prop_cfg.get("ical_url") and existing.ical_url != prop_cfg["ical_url"]:
                    existing.ical_url = prop_cfg["ical_url"]
                    session.commit()
                continue

            cleaner = prop_cfg.get("cleaner", {})
            prop = Property(
                name=prop_cfg["name"],
                address=prop_cfg.get("address", ""),
                ical_url=prop_cfg.get("ical_url"),
                bedrooms=prop_cfg.get("bedrooms", 1),
                max_guests=prop_cfg.get("max_guests", 4),
                base_price=prop_cfg.get("base_price", 100.0),
                cleaning_fee=prop_cfg.get("cleaning_fee", 0.0),
                wifi_password=prop_cfg.get("wifi_password"),
                lockbox_code=prop_cfg.get("lockbox_code"),
                checkout_time=prop_cfg.get("checkout_time", "11:00"),
                checkin_time=prop_cfg.get("checkin_time", "15:00"),
                cleaner_name=cleaner.get("name"),
                cleaner_phone=cleaner.get("phone"),
                cleaner_email=cleaner.get("email"),
                notes=prop_cfg.get("notes"),
            )
            session.add(prop)
            session.commit()
            logger.info("Seeded property: %s", prop.name)
    finally:
        session.close()


def seed_message_templates() -> None:
    """Ensure default message templates exist in DB."""
    default_templates = {
        "welcome": (
            "Hi {{ guest_name }},\n\n"
            "Welcome! We're excited to host you at {{ property_name }}.\n"
            "Your stay is confirmed from {{ checkin_date }} to {{ checkout_date }} "
            "({{ nights }} nights).\n\n"
            "I'll send check-in instructions closer to your arrival date.\n\n"
            "Let me know if you have any questions!\n"
        ),
        "check_in_instructions": (
            "Hi {{ guest_name }},\n\n"
            "Here are your check-in details for {{ property_name }}:\n\n"
            "Address: {{ address }}\n"
            "Check-in time: {{ checkin_time }}\n"
            "Lockbox code: {{ lockbox_code }}\n"
            "WiFi password: {{ wifi_password }}\n\n"
            "{{ notes }}\n\n"
            "Enjoy your stay!\n"
        ),
        "checkout_reminder": (
            "Hi {{ guest_name }},\n\n"
            "Just a friendly reminder that checkout is tomorrow at {{ checkout_time }}.\n\n"
            "Before you leave, please:\n"
            "- Start the dishwasher if there are dishes\n"
            "- Take out any trash\n"
            "- Lock the door behind you\n\n"
            "We hope you enjoyed your stay at {{ property_name }}!\n"
        ),
        "review_request": (
            "Hi {{ guest_name }},\n\n"
            "Thank you for staying at {{ property_name }}! "
            "We hope you had a wonderful time.\n\n"
            "If you have a moment, we'd really appreciate a review of your stay. "
            "Your feedback helps us improve and helps future guests.\n\n"
            "Thanks again, and we hope to host you again!\n"
        ),
    }

    session = get_session()
    try:
        for name, body in default_templates.items():
            existing = session.query(MessageTemplate).filter(MessageTemplate.name == name).first()
            if not existing:
                tmpl = MessageTemplate(name=name, body=body, channel="airbnb")
                session.add(tmpl)
        session.commit()
    finally:
        session.close()


# --- Dashboard Routes ---


@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Main dashboard overview."""
    session = get_session()
    try:
        properties = session.query(Property).all()
        today = date.today()

        upcoming_bookings = (
            session.query(Booking)
            .filter(Booking.checkin_date >= today, Booking.status == "confirmed")
            .order_by(Booking.checkin_date)
            .limit(10)
            .all()
        )

        active_bookings = (
            session.query(Booking)
            .filter(
                Booking.checkin_date <= today,
                Booking.checkout_date >= today,
                Booking.status == "confirmed",
            )
            .all()
        )

        pending_tasks = (
            session.query(CleaningTask)
            .filter(CleaningTask.status.in_(["pending", "notified"]))
            .order_by(CleaningTask.scheduled_date)
            .limit(10)
            .all()
        )

        pending_messages = (
            session.query(MessageLog)
            .filter(MessageLog.status == "queued")
            .order_by(MessageLog.scheduled_at)
            .limit(10)
            .all()
        )

        return templates.TemplateResponse("index.html", {
            "request": request,
            "properties": properties,
            "upcoming_bookings": upcoming_bookings,
            "active_bookings": active_bookings,
            "pending_tasks": pending_tasks,
            "pending_messages": pending_messages,
            "today": today,
        })
    finally:
        session.close()


@app.get("/bookings", response_class=HTMLResponse)
async def bookings_page(request: Request, property_id: int | None = None):
    """Bookings list page."""
    session = get_session()
    try:
        query = session.query(Booking).order_by(Booking.checkin_date.desc())
        if property_id:
            query = query.filter(Booking.property_id == property_id)
        bookings = query.limit(50).all()
        properties = session.query(Property).all()

        return templates.TemplateResponse("bookings.html", {
            "request": request,
            "bookings": bookings,
            "properties": properties,
            "selected_property_id": property_id,
        })
    finally:
        session.close()


@app.get("/cleaning", response_class=HTMLResponse)
async def cleaning_page(request: Request):
    """Cleaning tasks calendar."""
    session = get_session()
    try:
        tasks = (
            session.query(CleaningTask)
            .order_by(CleaningTask.scheduled_date.desc())
            .limit(50)
            .all()
        )
        properties = session.query(Property).all()
        prop_map = {p.id: p.name for p in properties}

        return templates.TemplateResponse("cleaning.html", {
            "request": request,
            "tasks": tasks,
            "prop_map": prop_map,
        })
    finally:
        session.close()


@app.post("/cleaning/{task_id}/complete")
async def complete_cleaning_task(task_id: int):
    """Mark a cleaning task as completed."""
    session = get_session()
    try:
        task = session.query(CleaningTask).get(task_id)
        if task:
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            session.commit()
    finally:
        session.close()
    return RedirectResponse("/cleaning", status_code=303)


@app.get("/messages", response_class=HTMLResponse)
async def messages_page(request: Request):
    """Guest messages queue."""
    session = get_session()
    try:
        messages = (
            session.query(MessageLog)
            .order_by(MessageLog.created_at.desc())
            .limit(50)
            .all()
        )
        return templates.TemplateResponse("messages.html", {
            "request": request,
            "messages": messages,
        })
    finally:
        session.close()


@app.post("/messages/{message_id}/mark-copied")
async def mark_message_copied(message_id: int):
    """Mark a message as copied (host sent it manually)."""
    session = get_session()
    try:
        msg = session.query(MessageLog).get(message_id)
        if msg:
            msg.status = "copied"
            msg.sent_at = datetime.now(timezone.utc)
            session.commit()
    finally:
        session.close()
    return RedirectResponse("/messages", status_code=303)


@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(
    request: Request,
    property_id: int | None = None,
    days: int = Query(default=30),
):
    """Pricing recommendations page."""
    session = get_session()
    try:
        properties = session.query(Property).all()
        recommendations = []

        if property_id and properties:
            engine = PricingEngine()
            start = date.today()
            end = start + timedelta(days=days)
            recommendations = engine.get_recommendations(property_id, start, end)
        elif properties:
            property_id = properties[0].id
            engine = PricingEngine()
            start = date.today()
            end = start + timedelta(days=days)
            recommendations = engine.get_recommendations(property_id, start, end)

        return templates.TemplateResponse("pricing.html", {
            "request": request,
            "properties": properties,
            "selected_property_id": property_id,
            "recommendations": recommendations,
            "days": days,
        })
    finally:
        session.close()


@app.get("/financial", response_class=HTMLResponse)
async def financial_page(
    request: Request,
    property_id: int | None = None,
    year: int | None = None,
    month: int | None = None,
):
    """Financial reports page."""
    session = get_session()
    try:
        properties = session.query(Property).all()
        today = date.today()
        year = year or today.year
        month = month or today.month

        tracker = FinancialTracker()
        report = None
        annual_report = None

        if property_id:
            report = tracker.get_monthly_report(property_id, year, month)
            annual_report = tracker.get_annual_report(property_id, year)
        elif properties:
            property_id = properties[0].id
            report = tracker.get_monthly_report(property_id, year, month)
            annual_report = tracker.get_annual_report(property_id, year)

        return templates.TemplateResponse("financial.html", {
            "request": request,
            "properties": properties,
            "selected_property_id": property_id,
            "year": year,
            "month": month,
            "report": report,
            "annual_report": annual_report,
            "categories": SCHEDULE_E_CATEGORIES,
        })
    finally:
        session.close()


@app.post("/financial/expense")
async def add_expense(
    request: Request,
    property_id: int = Form(...),
    category: str = Form(...),
    description: str = Form(...),
    amount: float = Form(...),
    expense_date: str = Form(...),
    vendor: str = Form(default=""),
):
    """Add an expense."""
    tracker = FinancialTracker()
    tracker.add_expense(
        property_id=property_id,
        category=category,
        description=description,
        amount=amount,
        expense_date=date.fromisoformat(expense_date),
        vendor=vendor or None,
    )
    return RedirectResponse(f"/financial?property_id={property_id}", status_code=303)


@app.post("/financial/payout")
async def add_payout(
    request: Request,
    property_id: int = Form(...),
    amount: float = Form(...),
    payout_date: str = Form(...),
    confirmation_code: str = Form(default=""),
    notes: str = Form(default=""),
):
    """Add a manual payout."""
    tracker = FinancialTracker()
    tracker.add_manual_payout(
        property_id=property_id,
        amount=amount,
        payout_date=date.fromisoformat(payout_date),
        confirmation_code=confirmation_code or None,
        notes=notes or None,
    )
    return RedirectResponse(f"/financial?property_id={property_id}", status_code=303)


@app.get("/financial/export/expenses")
async def export_expenses(property_id: int, year: int):
    """Export expenses as CSV."""
    tracker = FinancialTracker()
    csv_data = tracker.export_expenses_csv(property_id, year)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=expenses_{property_id}_{year}.csv"},
    )


@app.get("/financial/export/income")
async def export_income(property_id: int, year: int):
    """Export income as CSV."""
    tracker = FinancialTracker()
    csv_data = tracker.export_income_csv(property_id, year)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=income_{property_id}_{year}.csv"},
    )


@app.get("/maintenance", response_class=HTMLResponse)
async def maintenance_page(request: Request):
    """Maintenance tasks page."""
    session = get_session()
    try:
        tasks = (
            session.query(MaintenanceTask)
            .order_by(MaintenanceTask.created_at.desc())
            .limit(50)
            .all()
        )
        properties = session.query(Property).all()
        prop_map = {p.id: p.name for p in properties}

        return templates.TemplateResponse("maintenance.html", {
            "request": request,
            "tasks": tasks,
            "properties": properties,
            "prop_map": prop_map,
        })
    finally:
        session.close()


@app.post("/maintenance")
async def create_maintenance(
    property_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(default=""),
    priority: str = Form(default="normal"),
    cost: float = Form(default=0),
):
    """Create a maintenance task."""
    ops = OperationsManager()
    ops.create_maintenance_task(
        property_id=property_id,
        title=title,
        description=description or None,
        priority=priority,
        cost=cost if cost > 0 else None,
    )
    return RedirectResponse("/maintenance", status_code=303)


@app.post("/maintenance/{task_id}/complete")
async def complete_maintenance(task_id: int, cost: float = Form(default=0)):
    """Complete a maintenance task."""
    ops = OperationsManager()
    ops.complete_maintenance_task(task_id, cost=cost if cost > 0 else None)
    return RedirectResponse("/maintenance", status_code=303)


@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request):
    """Inventory management page."""
    session = get_session()
    try:
        items = session.query(InventoryItem).all()
        properties = session.query(Property).all()
        prop_map = {p.id: p.name for p in properties}

        return templates.TemplateResponse("inventory.html", {
            "request": request,
            "items": items,
            "properties": properties,
            "prop_map": prop_map,
        })
    finally:
        session.close()


@app.post("/inventory")
async def add_inventory_item(
    property_id: int = Form(...),
    name: str = Form(...),
    quantity: int = Form(default=0),
    reorder_threshold: int = Form(default=2),
    unit_cost: float = Form(default=0),
):
    """Add an inventory item."""
    session = get_session()
    try:
        item = InventoryItem(
            property_id=property_id,
            name=name,
            quantity=quantity,
            reorder_threshold=reorder_threshold,
            unit_cost=unit_cost if unit_cost > 0 else None,
        )
        session.add(item)
        session.commit()
    finally:
        session.close()
    return RedirectResponse("/inventory", status_code=303)


@app.post("/inventory/{item_id}/update")
async def update_inventory_item(item_id: int, quantity: int = Form(...)):
    """Update inventory quantity."""
    ops = OperationsManager()
    ops.update_inventory(item_id, quantity)
    return RedirectResponse("/inventory", status_code=303)


@app.post("/sync")
async def trigger_sync():
    """Manually trigger calendar sync."""
    syncer = CalendarSyncer()
    syncer.sync_all()
    return RedirectResponse("/", status_code=303)


def main() -> None:
    """Entry point for running the app."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    init_db()
    logger.info("Database initialized.")

    uvicorn.run(
        "proppilot.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
