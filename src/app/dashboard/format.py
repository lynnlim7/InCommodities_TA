"""Presentation formatting.

Pure functions over domain values, with no Streamlit import, so the rules a
trader reads off the screen are directly testable.

The core keeps its own period labels for diagnostics; the trader-facing
labels are built here from the half-open delivery interval instead, because
how a period is written is a presentation decision and the internal exclusive
end boundary must never reach the screen.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.core.models import DeliveryPeriod

PositionState = Literal["long", "short", "flat"]

TWO_PLACES = Decimal("0.01")


def format_daily_label(delivery: DeliveryPeriod) -> str:
    """A single delivery day: "01 Oct 2026"."""
    return f"{delivery.start:%d %b %Y}"


def format_weekly_label(delivery: DeliveryPeriod) -> str:
    """An inclusive delivery range: "01 Oct - 04 Oct 2026".

    The end shown is the last delivered day, not the exclusive boundary, so a
    bucket ending at [.., 05 Oct) reads as "- 04 Oct". The year is printed
    once unless the bucket straddles a year end, and a one-day bucket (which a
    Sunday as-of date produces) collapses to a single date.
    """
    last_day = delivery.end - timedelta(days=1)

    if last_day == delivery.start:
        return format_daily_label(delivery)

    if last_day.year != delivery.start.year:
        return f"{delivery.start:%d %b %Y} - {last_day:%d %b %Y}"

    return f"{delivery.start:%d %b} - {last_day:%d %b %Y}"


def format_monthly_label(delivery: DeliveryPeriod) -> str:
    """A calendar month: "Oct 2026".

    The first bucket may be clipped to the as-of date, but it still belongs to
    its calendar month and is labelled as that month.
    """
    return f"{delivery.start:%b %Y}"


def position_state(net_position_mw: Decimal) -> PositionState:
    """Classify a position for display.

    Read from the unrounded calculated value, so direction is never decided
    by a rounding artefact. This is presentation only: the domain has no
    long/short concept, just a signed MW number.
    """
    if net_position_mw > 0:
        return "long"

    if net_position_mw < 0:
        return "short"

    return "flat"


def format_position(net_position_mw: Decimal) -> str:
    """Format a position as signed MW to two places: "+10.00", "-5.00", "0.00".

    A long position carries an explicit "+" so its direction is readable
    without comparing it to its neighbours. A value too small to show at two
    places prints as "0.00" rather than "-0.00": the minus sign would be the
    only visible trace of a quantity that rounded away, and the row colour
    already carries the direction.
    """
    rounded = net_position_mw.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    if rounded > 0:
        return f"+{rounded:,.2f}"

    if rounded < 0:
        return f"{rounded:,.2f}"

    return "0.00"


def format_hours(hours: Decimal) -> str:
    """Format applicable delivery hours: "336", "1,680".

    Profile hours are whole hours in every configured profile, so the integer
    form is the normal case; the one-place fallback keeps a hypothetical
    half-hour window readable rather than printing an exponent.
    """
    if hours == hours.to_integral_value():
        return f"{hours:,.0f}"

    return f"{hours:,.1f}"
