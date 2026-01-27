# PropPilot — Next Steps for Property Managers

## Phase 1: Get Running (Day 1)

### 1. Set up your properties in `config.yaml`

For each property, you need:

- **iCal URL**: Go to Airbnb > Hosting > Calendar > Availability Settings > "Export Calendar". Copy the `.ics` link.
- **Base nightly price**: Your standard rate before adjustments.
- **Cleaner info**: Name, phone number (for SMS), email.
- **Access details**: WiFi password, lockbox code.
- **Check-in/out times**: Used in guest messages and cleaning scheduling.

Example for multiple properties:

```yaml
properties:
  - name: "Downtown Loft"
    address: "123 Main St, Apt 4B"
    ical_url: "https://www.airbnb.com/calendar/ical/YOUR_LISTING_ID.ics?s=YOUR_SECRET"
    base_price: 120.00
    cleaner:
      name: "Jane Doe"
      phone: "+15559876543"
  - name: "Beach House"
    address: "456 Ocean Dr"
    ical_url: "https://www.airbnb.com/calendar/ical/ANOTHER_ID.ics?s=SECRET"
    base_price: 200.00
    cleaner:
      name: "Bob Smith"
      phone: "+15551234567"
```

### 2. Set up a dedicated Gmail for Airbnb notifications

1. Create a new Gmail account (e.g., `myproperties.airbnb@gmail.com`)
2. In Gmail: Settings > "See all settings" > Forwarding and POP/IMAP > Enable IMAP
3. Create an App Password: Google Account > Security > 2-Step Verification > App Passwords
4. In your Airbnb account: Settings > Notifications > Set email to this new Gmail
5. Add credentials to `.env`:
   ```
   IMAP_HOST=imap.gmail.com
   IMAP_USER=myproperties.airbnb@gmail.com
   IMAP_PASSWORD=your-16-char-app-password
   ```

### 3. Set up Twilio for cleaner SMS (optional but recommended)

1. Create a Twilio account at https://www.twilio.com
2. Get a phone number (trial accounts give you one free)
3. On trial: verify your cleaner's phone number in Twilio console
4. Add to `.env`:
   ```
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your-token
   TWILIO_FROM_NUMBER=+15551234567
   ```

### 4. Start PropPilot

```bash
pip install -e .
proppilot
```

Open http://127.0.0.1:8000 — you should see your properties listed on the dashboard.

---

## Phase 2: Customize Messages (Week 1)

### Edit guest message templates

Templates are in `src/proppilot/config/templates/`:

- `welcome.txt` — Sent when a booking is confirmed
- `check_in_instructions.txt` — Sent 24 hours before check-in
- `checkout_reminder.txt` — Sent evening before checkout
- `review_request.txt` — Sent 48 hours after checkout

Each template uses Jinja2 variables:

| Variable | Description |
|---|---|
| `{{ guest_name }}` | Guest's name (from email parsing, or "Guest") |
| `{{ property_name }}` | Property name from config |
| `{{ address }}` | Property address |
| `{{ checkin_date }}` | Formatted check-in date |
| `{{ checkout_date }}` | Formatted checkout date |
| `{{ checkin_time }}` | Check-in time (e.g., "15:00") |
| `{{ checkout_time }}` | Checkout time (e.g., "11:00") |
| `{{ wifi_password }}` | WiFi password from config |
| `{{ lockbox_code }}` | Lockbox code from config |
| `{{ nights }}` | Number of nights |
| `{{ notes }}` | Property notes from config |
| `{{ confirmation_code }}` | Airbnb confirmation code (if parsed from email) |

### Adjust message timing

In `config.yaml`:

```yaml
messages:
  check_in_instructions:
    trigger_hours_before_checkin: 24    # Send 1 day before
    send_at_hour: 14                    # At 2 PM
  checkout_reminder:
    trigger_hours_before_checkout: 18   # Evening before
    send_at_hour: 18                    # At 6 PM
  review_request:
    trigger_hours_after_checkout: 48    # 2 days after checkout
```

---

## Phase 3: Tune Pricing (Week 2)

### Adjust pricing rules in `config.yaml`

```yaml
pricing:
  weekend_multiplier: 1.15        # Fri/Sat nights +15%
  last_minute_discount: 0.10      # Within 3 days: -10%
  last_minute_days: 3
  far_out_premium: 0.05           # 60+ days out: +5%
  far_out_days: 60
  high_season:
    months: [6, 7, 8, 12]         # Your high season months
    multiplier: 1.25              # +25%
  low_season:
    months: [1, 2, 3]             # Your low season months
    multiplier: 0.85              # -15%
  min_price_ratio: 0.70           # Never below 70% of base
  max_price_ratio: 2.00           # Never above 200% of base
```

### Add custom pricing rules via the database

For event-specific pricing (concerts, festivals, holidays), add rules through the SQLite database or extend the dashboard to include a pricing rule form.

### Review recommendations

Visit the **Pricing** page on the dashboard. For each date, you'll see:
- Base price
- Recommended price
- Each adjustment that was applied (weekend, season, lead time, etc.)

Apply changes manually on Airbnb.

---

## Phase 4: Track Finances (Month 1)

### Enter expenses regularly

Use the **Financial** page to log expenses in IRS Schedule E categories:
- Advertising
- Cleaning and maintenance
- Insurance
- Legal and professional fees
- Management fees
- Mortgage interest
- Repairs
- Supplies
- Taxes
- Utilities

### Set up recurring expenses

For monthly costs (mortgage, insurance, utilities), note them and enter them each month. A future update will auto-generate recurring expenses.

### Export for taxes

At tax time:
1. Go to **Financial** page
2. Select the property and year
3. Click **Export Expenses CSV** and **Export Income CSV**
4. The expense categories map directly to IRS Schedule E line items

---

## Phase 5: Optimize Operations (Month 2+)

### Monitor the email parser

The parser logs all processed emails. Check for "unrecognized" entries — this means Airbnb changed their email format. You'll need to update regex patterns in `src/proppilot/modules/email_parser/parser.py`.

### Track inventory

Use the **Inventory** page to track supplies per property (toilet paper, towels, cleaning products). Set reorder thresholds so you get alerts before running out.

### Maintenance tracking

Log maintenance issues as they arise. Track costs per property to understand your true operating expenses.

---

## Future Enhancements to Consider

| Enhancement | Effort | Impact |
|---|---|---|
| Add VRBO/Booking.com iCal feeds | Low | Support multi-platform listings |
| Cleaner SMS reply confirmation | Medium | Auto-complete tasks when cleaner replies "DONE" |
| Photo upload after cleaning | Medium | Verification and damage documentation |
| Guest contact info capture form | Low | Enable direct SMS/email to guests |
| Dashboard authentication | Medium | Multi-user access, owner reports |
| Mobile-responsive CSS | Medium | Phone-friendly dashboard |
| Recurring expense automation | Low | Auto-generate monthly costs |
| Revenue per available night metric | Low | Better portfolio performance tracking |
| Owner-specific financial reports | Medium | For managing others' properties |
| Dynamic pricing with market data | High | AirDNA integration for competitor rates |

---

## Troubleshooting

### iCal not syncing
- Verify the iCal URL works by pasting it in a browser — it should download a `.ics` file
- Check the app logs for HTTP errors
- Airbnb iCal feeds can lag 15 minutes to several hours

### Email parser not finding emails
- Verify IMAP credentials by testing with a mail client
- Check that Airbnb notifications are going to the right Gmail
- Look at the `email_processing_log` table for error entries

### Twilio SMS not sending
- Verify credentials in `.env`
- On trial accounts, the recipient number must be verified in Twilio console
- Check app logs for Twilio API errors

### Database issues
- The SQLite database is at `proppilot.db` in the project root
- To reset: delete the file and restart — tables will be recreated
- For migrations: `alembic upgrade head` (after creating migration scripts)
