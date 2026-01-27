"""Tests for the pricing engine."""

from datetime import date

from proppilot.models.property import Property
from proppilot.models.task import PriceOverride, PricingRule
from proppilot.modules.pricing.engine import PricingEngine


def test_weekend_pricing():
    engine = PricingEngine()
    prop = Property(
        id=1, name="Test", address="123 Test", base_price=100.0,
        bedrooms=1, max_guests=4, checkout_time="11:00", checkin_time="15:00",
    )

    # Saturday, Jul 4 2026 (high season, avoids low-season/occupancy drag)
    rec = engine._calculate_price(prop, date(2026, 7, 4), {}, [], set())
    # Weekend multiplier stacked with high season should push above base
    assert rec.recommended_price > 100.0
    assert any("Weekend" in adj for adj in rec.adjustments)


def test_weekday_no_weekend_premium():
    engine = PricingEngine()
    prop = Property(
        id=1, name="Test", address="123 Test", base_price=100.0,
        bedrooms=1, max_guests=4, checkout_time="11:00", checkin_time="15:00",
    )

    # Wednesday, Feb 4 2026
    rec = engine._calculate_price(prop, date(2026, 2, 4), {}, [], set())
    # Low season (Feb in low_season months [1,2,3]), no weekend
    assert not any("Weekend" in adj for adj in rec.adjustments)


def test_override_takes_precedence():
    engine = PricingEngine()
    prop = Property(
        id=1, name="Test", address="123 Test", base_price=100.0,
        bedrooms=1, max_guests=4, checkout_time="11:00", checkin_time="15:00",
    )
    target = date(2026, 2, 14)
    override = PriceOverride(
        id=1, property_id=1, date=target, price=200.0, reason="Valentine's Day"
    )

    rec = engine._calculate_price(prop, target, {target: override}, [], set())
    assert rec.recommended_price == 200.0
    assert rec.override_price == 200.0


def test_price_floor_and_ceiling():
    engine = PricingEngine()
    prop = Property(
        id=1, name="Test", address="123 Test", base_price=100.0,
        bedrooms=1, max_guests=4, checkout_time="11:00", checkin_time="15:00",
    )

    # The min ratio is 0.70, max is 2.00
    # Even with extreme multipliers, price should stay within bounds
    rec = engine._calculate_price(prop, date(2026, 2, 4), {}, [], set())
    assert rec.recommended_price >= 100.0 * 0.70
    assert rec.recommended_price <= 100.0 * 2.00


def test_high_season_multiplier():
    engine = PricingEngine()
    prop = Property(
        id=1, name="Test", address="123 Test", base_price=100.0,
        bedrooms=1, max_guests=4, checkout_time="11:00", checkin_time="15:00",
    )

    # July is high season (month 7)
    # Use a Wednesday to avoid weekend multiplier
    rec = engine._calculate_price(prop, date(2026, 7, 1), {}, [], set())
    assert any("High season" in adj for adj in rec.adjustments)
    assert rec.recommended_price > 100.0
