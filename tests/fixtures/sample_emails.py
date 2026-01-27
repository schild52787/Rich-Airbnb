"""Sample Airbnb email content for testing the email parser."""

BOOKING_CONFIRMATION_SUBJECT = "Reservation confirmed - John Doe arrives Feb 1"

BOOKING_CONFIRMATION_BODY = """
Hi Host,

You have a new reservation!

Guest: John Doe
Confirmation code: HMXA1234AB

Check-in: February 1, 2026
Check-out: February 5, 2026

Total payout: $480.00

View reservation details on Airbnb.

Thanks,
The Airbnb Team
"""

PAYOUT_SUBJECT = "Your payout of $480.00 has been sent"

PAYOUT_BODY = """
Hi Host,

Your payout of $480.00 for reservation HMXA1234AB has been sent
to your bank account ending in ****1234.

The transfer should arrive within 1-2 business days.

Thanks,
The Airbnb Team
"""

CANCELLATION_SUBJECT = "Reservation cancelled - Jane Smith"

CANCELLATION_BODY = """
Hi Host,

Jane Smith has cancelled their reservation.

Confirmation code: HMXB5678CD
Original dates: February 10-12, 2026

Please check your cancellation policy for details on any payout.

Thanks,
The Airbnb Team
"""
