"""Rule-based price recommendation engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from proppilot.config import settings
from proppilot.database import get_session
from proppilot.models.booking import Booking
from proppilot.models.property import Property
from proppilot.models.task import PriceOverride, PricingRule

logger = logging.getLogger(__name__)


@dataclass
class PriceRecommendation:
    property_id: int
    date: date
    base_price: float
    recommended_price: float
    adjustments: list[str]  # Descriptions of applied adjustments
    override_price: float | None = None  # Manual override if set


class PricingEngine:
    """Calculates recommended nightly prices based on configurable rules."""

    def __init__(self) -> None:
        self._config = settings.get("pricing", {})

    def get_recommendations(
        self, property_id: int, start_date: date, end_date: date
    ) -> list[PriceRecommendation]:
        """Get price recommendations for a date range."""
        session = get_session()
        try:
            prop = session.get(Property, property_id)
            if not prop:
                return []

            overrides = self._get_overrides(session, property_id, start_date, end_date)
            custom_rules = (
                session.query(PricingRule)
                .filter(
                    PricingRule.property_id == property_id,
                    PricingRule.is_active.is_(True),
                )
                .all()
            )

            # Get existing bookings for occupancy calculation
            bookings = (
                session.query(Booking)
                .filter(
                    Booking.property_id == property_id,
                    Booking.status == "confirmed",
                    Booking.checkout_date >= start_date,
                    Booking.checkin_date <= end_date,
                )
                .all()
            )
            booked_dates = set()
            for b in bookings:
                d = b.checkin_date
                while d < b.checkout_date:
                    booked_dates.add(d)
                    d += timedelta(days=1)

            recommendations = []
            current = start_date
            while current <= end_date:
                rec = self._calculate_price(
                    prop, current, overrides, custom_rules, booked_dates
                )
                recommendations.append(rec)
                current += timedelta(days=1)

            return recommendations
        finally:
            session.close()

    def _calculate_price(
        self,
        prop: Property,
        target_date: date,
        overrides: dict[date, PriceOverride],
        custom_rules: list[PricingRule],
        booked_dates: set[date],
    ) -> PriceRecommendation:
        """Calculate recommended price for a single date."""
        base = prop.base_price
        multiplier = 1.0
        adjustments: list[str] = []

        # Manual override takes precedence
        override = overrides.get(target_date)
        if override:
            return PriceRecommendation(
                property_id=prop.id,
                date=target_date,
                base_price=base,
                recommended_price=override.price,
                adjustments=[f"Manual override: {override.reason or 'custom'}"],
                override_price=override.price,
            )

        # Weekend premium (Friday=4, Saturday=5)
        if target_date.weekday() in (4, 5):
            weekend_mult = self._config.get("weekend_multiplier", 1.15)
            multiplier *= weekend_mult
            adjustments.append(f"Weekend: +{(weekend_mult - 1) * 100:.0f}%")

        # Seasonal adjustments
        month = target_date.month
        high_season = self._config.get("high_season", {})
        low_season = self._config.get("low_season", {})

        if month in high_season.get("months", []):
            seasonal = high_season.get("multiplier", 1.25)
            multiplier *= seasonal
            adjustments.append(f"High season: +{(seasonal - 1) * 100:.0f}%")
        elif month in low_season.get("months", []):
            seasonal = low_season.get("multiplier", 0.85)
            multiplier *= seasonal
            adjustments.append(f"Low season: {(seasonal - 1) * 100:.0f}%")

        # Lead time adjustments
        days_out = (target_date - date.today()).days
        last_minute_days = self._config.get("last_minute_days", 3)
        far_out_days = self._config.get("far_out_days", 60)

        if 0 < days_out <= last_minute_days:
            discount = self._config.get("last_minute_discount", 0.10)
            multiplier *= (1 - discount)
            adjustments.append(f"Last minute ({days_out}d): -{discount * 100:.0f}%")
        elif days_out > far_out_days:
            premium = self._config.get("far_out_premium", 0.05)
            multiplier *= (1 + premium)
            adjustments.append(f"Far out ({days_out}d): +{premium * 100:.0f}%")

        # Occupancy-based adjustment (trailing 30 days)
        trailing_start = target_date - timedelta(days=30)
        trailing_booked = sum(
            1 for d in booked_dates
            if trailing_start <= d <= target_date
        )
        occupancy_rate = trailing_booked / 30.0
        if occupancy_rate > 0.80:
            occ_mult = 1.10
            multiplier *= occ_mult
            adjustments.append(f"High occupancy ({occupancy_rate:.0%}): +10%")
        elif occupancy_rate < 0.40:
            occ_mult = 0.95
            multiplier *= occ_mult
            adjustments.append(f"Low occupancy ({occupancy_rate:.0%}): -5%")

        # Apply custom rules from DB
        for rule in custom_rules:
            if not self._rule_applies(rule, target_date):
                continue
            multiplier *= rule.multiplier
            adjustments.append(f"{rule.name}: x{rule.multiplier:.2f}")

        # Calculate final price with floor/ceiling
        recommended = base * multiplier
        min_ratio = self._config.get("min_price_ratio", 0.70)
        max_ratio = self._config.get("max_price_ratio", 2.00)
        recommended = max(base * min_ratio, min(recommended, base * max_ratio))
        recommended = round(recommended, 2)

        return PriceRecommendation(
            property_id=prop.id,
            date=target_date,
            base_price=base,
            recommended_price=recommended,
            adjustments=adjustments,
        )

    def _rule_applies(self, rule: PricingRule, target_date: date) -> bool:
        """Check if a custom pricing rule applies to a target date."""
        if rule.start_date and target_date < rule.start_date:
            return False
        if rule.end_date and target_date > rule.end_date:
            return False
        if rule.days_of_week:
            allowed_days = {int(d) for d in rule.days_of_week.split(",")}
            if target_date.weekday() not in allowed_days:
                return False
        return True

    def _get_overrides(
        self, session: Session, property_id: int, start: date, end: date
    ) -> dict[date, PriceOverride]:
        """Get price overrides for a date range."""
        overrides = (
            session.query(PriceOverride)
            .filter(
                PriceOverride.property_id == property_id,
                PriceOverride.date >= start,
                PriceOverride.date <= end,
            )
            .all()
        )
        return {o.date: o for o in overrides}
