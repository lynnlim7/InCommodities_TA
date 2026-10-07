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
ENERGY_PRECISION = Decimal("1")

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
    """Signed average net power, at two decimal places."""
    return _format_signed(net_position_mw, POSITION_PRECISION)


def format_energy(net_position_mwh: Decimal) -> str:
    """Signed net energy, at whole MWh."""
    return _format_signed(net_position_mwh, ENERGY_PRECISION)


def _format_signed(value: Decimal, precision: Decimal) -> str:
    """Render a signed quantity at one precision, without a signed zero.

    A long is always printed with an explicit ``+`` so direction is readable
    without comparing against the neighbouring rows. A value too small to
    print is shown unsigned: "-0" would imply a short the number does not
    support, and the row colour still reports the real direction.
    """

    rounded = value.quantize(
        precision, 
        rounding=ROUND_HALF_UP
        )

    places = max(-int(precision.as_tuple().exponent), 0)

    if rounded > 0:
        return f"+{rounded:,.{places}f}"

    if rounded < 0:
        return f"{rounded:,.{places}f}"

    return f"{abs(rounded):,.{places}f}"
