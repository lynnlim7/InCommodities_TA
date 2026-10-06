"""
Presentation formatting.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.core.models import DeliveryPeriod

PositionState = Literal["long", "short", "flat"]

POSITION_PRECISION = Decimal("0.01")

def format_daily_label(delivery: DeliveryPeriod) -> str:
    """A single delivery day: "01 Oct 2026"."""
    return f"{delivery.start:%d %b %Y}"


def format_weekly_label(delivery: DeliveryPeriod) -> str:

    last_day = delivery.end - timedelta(days=1)

    if last_day == delivery.start:
        return format_daily_label(delivery)

    if last_day.year != delivery.start.year:
        return f"{delivery.start:%d %b %Y} - {last_day:%d %b %Y}"

    return f"{delivery.start:%d %b} - {last_day:%d %b %Y}"


def format_monthly_label(delivery: DeliveryPeriod) -> str:

    return f"{delivery.start:%b %Y}"


def position_state(net_position_mw: Decimal) -> PositionState:

    if net_position_mw > 0:
        return "long"

    if net_position_mw < 0:
        return "short"

    return "flat"


def format_position(net_position_mw: Decimal) -> str:

    rounded = net_position_mw.quantize(
        POSITION_PRECISION, 
        rounding=ROUND_HALF_UP
        )

    if rounded > 0:
        return f"+{rounded:,.2f}"

    if rounded < 0:
        return f"{rounded:,.2f}"

    return "0.00"


def format_hours(hours: Decimal) -> str:
    
    if hours == hours.to_integral_value():
        return f"{hours:,.0f}"

    return f"{hours:,.1f}"
