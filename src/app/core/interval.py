"""Half-open date intervals.

One type serves both trade delivery periods and reporting periods, because the position
calculation only ever asks the same question of them: where do they overlap? Keeping a
single interval type means the inclusive-start/exclusive-end rule is implemented and
tested exactly once (requirements.md S5.1, AC-04).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.core.errors import InvalidIntervalError

HOURS_PER_DAY = 24
"""All date boundaries fall at 00:00 JST, so a calendar day is always 24 hours.

Japan does not observe daylight saving time, so this holds for every delivery day in
scope and no timezone arithmetic is required (requirements.md S5.1).
"""


@dataclass(frozen=True, slots=True, order=True)
class DateInterval:
    """A date range covering ``[start, end)``: start included, end excluded.

    The exclusive end is the CSV's own convention -- ``end_date`` is documented as the
    day *after* the last delivery day -- so storing it unmodified avoids an off-by-one
    translation at every use site.
    """

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise InvalidIntervalError(
                f"interval must satisfy start < end, got start={self.start.isoformat()} "
                f"end={self.end.isoformat()} (end is exclusive, so an empty interval is "
                f"not a valid delivery or reporting period)"
            )

    @property
    def days(self) -> int:
        """Number of delivery days covered. Always >= 1 given the start < end invariant."""
        return (self.end - self.start).days

    @property
    def hours(self) -> Decimal:
        """Wall-clock hours spanned, used as the Average MW denominator (S6.3)."""
        return Decimal(self.days * HOURS_PER_DAY)

    @property
    def last_day(self) -> date:
        """The final delivery day, inclusive. For presenting ranges to humans (S8.1)."""
        return self.end - timedelta(days=1)

    def intersection(self, other: DateInterval) -> DateInterval | None:
        """The overlap with ``other``, or None when they do not overlap.

        Returning None rather than an empty interval keeps the "no exposure" case
        explicit at the call site and preserves the start < end invariant: there is no
        such thing as a zero-length DateInterval.
        """
        start = max(self.start, other.start)
        end = min(self.end, other.end)
        if start >= end:
            return None
        return DateInterval(start, end)

    def __str__(self) -> str:
        return f"[{self.start.isoformat()}, {self.end.isoformat()})"
