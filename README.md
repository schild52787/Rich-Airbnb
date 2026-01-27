# PropPilot - Airbnb Property Management Automation

A modular Python application that automates guest communication, calendar management, cleaning coordination, pricing recommendations, and financial tracking for 2-5 Airbnb properties. Runs as a local web dashboard backed by SQLite.

## Key Features

- **Automatic booking detection** via Airbnb iCal feeds (polled every 15 minutes)
- **Email parsing** of Airbnb notifications for guest names, confirmation codes, and payouts
- **Cleaning task automation** with SMS notifications to cleaners via Twilio
- **Guest message templates** prepared for copy-paste into Airbnb (welcome, check-in instructions, checkout reminder, review request)
- **Rule-based pricing recommendations** with seasonal, weekend, lead-time, and occupancy adjustments
- **Financial tracking** with IRS Schedule E categories, monthly/annual reports, and CSV export
- **Maintenance & inventory management** with reorder alerts
- **Web dashboard** with 8 pages for full property management visibility

## How It Works

PropPilot works around Airbnb's lack of a public host API:

| Data Source | Method | What It Provides |
|---|---|---|
| **iCal feeds** | Public URL per listing | Booking dates, calendar blocks |
| **Email parsing** | IMAP to a dedicated Gmail | Guest names, confirmation codes, payout amounts |
| **Manual entry** | Dashboard forms | Expenses, payouts, maintenance tasks, inventory |

Modules communicate through an internal event bus:

```
Airbnb iCal Feed ──> Calendar Sync ──> Event Bus ──> Guest Comms (queue messages)
                                           ├──────> Operations (create cleaning tasks)
                                           └──────> Financial (link bookings)

Airbnb Emails ────> Email Parser ───> Event Bus ──> Financial (log payouts)
                                           └──────> Enrich bookings (guest names)
```

**Important constraints:**
- Messages are **prepared for copy-paste**, not sent automatically through Airbnb
- Pricing is **recommendation-only** — you apply changes manually
- Email parsing is **fragile** — Airbnb changes formats; unrecognized emails are logged for review

## Quick Start

### Prerequisites

- Python 3.11+
- A Gmail account dedicated to receiving Airbnb notification emails
- (Optional) Twilio account for SMS to cleaners

### Installation

```bash
git clone https://github.com/schild52787/Rich-Airbnb.git
cd Rich-Airbnb
pip install -e .
```

### Configuration

1. **Copy the environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env`** with your credentials:
   - IMAP credentials for the Gmail that receives Airbnb notifications
   - Twilio credentials for cleaner SMS (optional)
   - SMTP credentials for direct guest emails (optional)

3. **Edit `config.yaml`** with your property details:
   - Property name, address, base price
   - iCal URL (from Airbnb > Hosting > Calendar > Export Calendar)
   - Cleaner contact info
   - WiFi password and lockbox code
   - Pricing rules and message timing

### Running

```bash
proppilot
```

Opens the dashboard at **http://127.0.0.1:8000**

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Project Structure

```
proppilot/
├── config.yaml                    # Property details, pricing rules, schedules
├── .env                           # Secrets (not committed)
├── pyproject.toml                 # Dependencies and project metadata
├── src/proppilot/
│   ├── app.py                     # FastAPI app + routes + startup
│   ├── config.py                  # YAML + .env loader
│   ├── database.py                # SQLAlchemy engine/session
│   ├── events.py                  # In-process pub/sub event bus
│   ├── scheduler.py               # APScheduler background jobs
│   ├── models/                    # SQLAlchemy models (12 tables)
│   ├── modules/
│   │   ├── calendar_sync/         # iCal fetch + diff → booking events
│   │   ├── email_parser/          # IMAP + Airbnb email pattern matching
│   │   ├── guest_comms/           # Templates + message queue
│   │   ├── operations/            # Cleaning, maintenance, inventory
│   │   ├── pricing/               # Rule-based price recommender
│   │   └── financial/             # Income/expense tracking + reports
│   ├── dashboard/
│   │   ├── templates/             # Jinja2 HTML (8 pages)
│   │   └── static/               # CSS
│   └── config/templates/          # Guest message templates
├── tests/                         # 30 tests with fixtures
└── alembic/                       # Database migrations
```

## Dashboard Pages

| Page | What It Shows |
|---|---|
| **Dashboard** | Active guests, upcoming bookings, pending tasks, queued messages |
| **Bookings** | All bookings with guest info, dates, payouts, status |
| **Cleaning** | Task calendar, turnover flags, cleaner notification status |
| **Messages** | Queued messages with expand-to-copy workflow |
| **Pricing** | Date-by-date recommended prices with adjustment breakdowns |
| **Financial** | Monthly/annual reports, expense/payout entry, CSV export |
| **Maintenance** | Repair task CRUD with priority and cost |
| **Inventory** | Supply tracking with reorder alerts |

## Tech Stack

| Component | Library |
|---|---|
| Web framework | FastAPI + Jinja2 |
| Database | SQLite via SQLAlchemy |
| Scheduler | APScheduler |
| iCal parsing | icalendar |
| Email reading | imap-tools |
| SMS | Twilio |
| HTTP client | httpx |
| Config | PyYAML + python-dotenv |

## Security Notes

- `.env` contains credentials — **never commit it**
- `config.yaml` contains lockbox codes and WiFi passwords — consider encrypting or restricting access
- The dashboard has no authentication — only run on localhost or behind a VPN
