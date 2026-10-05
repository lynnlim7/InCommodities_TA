"""Display formatting: the only place in the application that rounds.

requirements.md S5.4 requires aggregation to use unrounded values and rounding to be
presentation-only, with a documented and consistent displayed precision. Keeping every
rounding decision in this one module is what makes that claim checkable.

Displayed precision:

* **Average MW** -- 2 decimal places. It is a ratio and often repeats, so some precision
  must be dropped; two places is finer than any hedging decision needs.
* **Net MWh** -- whole MWh. The supplied book yields exact integers, and a trader scanning
  three tables does not want two digits of noise on a five-digit number. A value that is
  non-zero but would round to zero falls back to 2 decimal places, so a small real
  position is never displayed as "0" beside a LONG label.

Rounding is half-up rather than Python's default banker's rounding, because half-up is
what a reader checking a figure by hand will expect.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core import Position, ReportPeriod

MW_PLACES = Decimal("0.01")
MWH_PLACES = Decimal("1")
MWH_FALLBACK_PLACES = Decimal("0.01")

PARTIAL_MARKER = "*"
"""Appended to a partial period's label; S8.3 requires partial periods be identified."""

_GLYPHS = {Position.LONG: "▲", Position.SHORT: "▼", Position.FLAT: "·"}
_STYLES = {Position.LONG: "green", Position.SHORT: "red", Position.FLAT: "dim"}


def format_mw(value: Decimal) -> str:
    """Average MW to two places, with an explicit sign and thousands separators."""
    return _with_separators(value.quantize(MW_PLACES, rounding=ROUND_HALF_UP), places=2)


def format_mwh(value: Decimal) -> str:
    """Net MWh to whole units, widening to two places rather than displaying a false zero."""
    rounded = value.quantize(MWH_PLACES, rounding=ROUND_HALF_UP)
    if rounded == 0 and value != 0:
        return _with_separators(
            value.quantize(MWH_FALLBACK_PLACES, rounding=ROUND_HALF_UP), places=2
        )
    return _with_separators(rounded, places=0)


def position_text(position: Position) -> str:
    """The position as a word plus a shape.

    Both are always present because S8.3 forbids relying on colour or sign alone: the
    output must still be unambiguous in a monochrome terminal or a printout.
    """
    return f"{position.value} {_GLYPHS[position]}"


def position_legend() -> str:
    """Shape-to-word legend, for a view too narrow to carry the word on every row."""
    return "  ".join(f"{_GLYPHS[position]} {position.value}" for position in Position)


def position_style(position: Position) -> str:
    """A colour for the position. Always redundant with the word, never a substitute."""
    return _STYLES[position]


def period_label(period: ReportPeriod) -> str:
    """The period's label, marked when the period is clipped by the as-of date."""
    return f"{period.label} {PARTIAL_MARKER}" if period.is_partial else period.label


def covered_dates(period: ReportPeriod) -> str:
    """Covered start and end as inclusive dates (S8.1).

    Inclusive because this is read by humans: the exclusive end that the data model uses
    would invite a reader to think delivery continues into that day. Machine output keeps
    the exclusive form.
    """
    if period.interval.days == 1:
        return period.start.isoformat()
    return f"{period.start.isoformat()} to {period.last_day.isoformat()}"


def format_date(value: date) -> str:
    return value.isoformat()


def _with_separators(value: Decimal, places: int) -> str:
    """Render a quantized Decimal with thousands separators and an explicit sign."""
    return f"{value:+,.{places}f}" if value != 0 else f"{value:,.{places}f}"
