"""Tests for email parser pattern matching."""

import re

from proppilot.modules.email_parser.parser import (
    CHECKIN_DATE_RE,
    CHECKOUT_DATE_RE,
    CONFIRMATION_CODE_RE,
    GUEST_NAME_RE,
    PATTERNS,
    PAYOUT_AMOUNT_RE,
    _try_parse_date,
)
from tests.fixtures.sample_emails import (
    BOOKING_CONFIRMATION_BODY,
    BOOKING_CONFIRMATION_SUBJECT,
    CANCELLATION_SUBJECT,
    PAYOUT_BODY,
    PAYOUT_SUBJECT,
)
from datetime import date


def test_classify_booking_confirmation():
    assert PATTERNS["booking_confirmation"].search(BOOKING_CONFIRMATION_SUBJECT)


def test_classify_payout():
    assert PATTERNS["payout"].search(PAYOUT_SUBJECT)


def test_classify_cancellation():
    assert PATTERNS["cancellation"].search(CANCELLATION_SUBJECT)


def test_extract_confirmation_code():
    match = CONFIRMATION_CODE_RE.search(BOOKING_CONFIRMATION_BODY)
    assert match
    assert match.group(1) == "HMXA1234AB"


def test_extract_guest_name():
    match = GUEST_NAME_RE.search(BOOKING_CONFIRMATION_BODY)
    assert match
    assert match.group(1) == "John Doe"


def test_extract_payout_amount():
    match = PAYOUT_AMOUNT_RE.search(PAYOUT_BODY)
    assert match
    assert float(match.group(1)) == 480.00


def test_extract_checkin_date():
    match = CHECKIN_DATE_RE.search(BOOKING_CONFIRMATION_BODY)
    assert match
    parsed = _try_parse_date(match.group(1))
    assert parsed == date(2026, 2, 1)


def test_extract_checkout_date():
    match = CHECKOUT_DATE_RE.search(BOOKING_CONFIRMATION_BODY)
    assert match
    parsed = _try_parse_date(match.group(1))
    assert parsed == date(2026, 2, 5)


def test_try_parse_date_formats():
    assert _try_parse_date("February 1, 2026") == date(2026, 2, 1)
    assert _try_parse_date("Feb 1, 2026") == date(2026, 2, 1)
    assert _try_parse_date("invalid") is None
