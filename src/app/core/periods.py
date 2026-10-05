"""Reporting windows: the daily, weekly, and monthly periods a run reports on.

Window generation is deliberately separate from position calculation (requirements.md
S13.4). The engine asks only "which intervals am I reporting on?" and never knows whether
an interval came from a day, a week, or a clipped month, which is why the same summation
serves all three views.

Everything here is a pure function of an explicit ``as_of`` plus a ``ReportingConfig``.
Nothing reads the system clock, so a run is fully reproducible (S13.2).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from app.config import DEFAULT_REPORTING_CONFIG, ReportingConfig
from app.core.interval import DateInterval


class Granularity(Enum):
    """The three forward-looking views the brief asks for (requirements.md S3.1)."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass(frozen=True, slots=True)
class ReportPeriod:
    """One reported row's period: a label plus the interval actually covered.

    ``interval`` is the *covered* interval, already clipped to the as-of date. A trader
    reading a week row needs to know it covers four days rather than seven, so the
    covered dates travel with the period instead of being recomputed for display
    (requirements.md S7.2, S8.1).
    """

    label: str
    interval: DateInterval
    granularity: Granularity
    is_partial: bool
    """True when the period was clipped because it began before the as-of date.

    Flagged rather than hidden: a partial week's MWh is not comparable with a full week's,
    so S8.3 requires partial periods be clearly identified.
    """

    @property
    def start(self) -> date:
        """First covered day, inclusive."""
        return self.interval.start

    @property
    def last_day(self) -> date:
        """Final covered day, inclusive -- the form shown to humans (S8.1)."""
        return self.interval.last_day

    @property
    def end_exclusive(self) -> date:
        """Day after the final covered day -- the form used in machine output (S8.1)."""
        return self.interval.end


def daily_periods(
    as_of: date, config: ReportingConfig = DEFAULT_REPORTING_CONFIG
) -> tuple[ReportPeriod, ...]:
    """Consecutive single days starting on the as-of date (requirements.md S7.1).

    The as-of day is included because the tool is read each morning and the trader needs
    today's position in order to hedge it. No day is ever partial: the brief supplies an
    as-of date rather than an intraday timestamp, and inventing partial-day treatment is
    explicitly out of scope (S7.4).
    """
    periods = []
    for offset in range(config.daily_count):
        day = as_of + timedelta(days=offset)
        periods.append(
            ReportPeriod(
                label=day.isoformat(),
                interval=DateInterval(day, day + timedelta(days=1)),
                granularity=Granularity.DAILY,
                is_partial=False,
            )
        )
    return tuple(periods)


def weekly_periods(
    as_of: date, config: ReportingConfig = DEFAULT_REPORTING_CONFIG
) -> tuple[ReportPeriod, ...]:
    """The current calendar week plus the following weeks (requirements.md S7.2).

    Weeks run Monday to Sunday by default. The first week is clipped at the as-of date:
    including the days already delivered would report volume the desk can no longer act
    on, and would make the row's MWh look larger than the remaining exposure.
    """
    week_start = _start_of_week(as_of, config.week_start)
    periods = []
    for index in range(config.weekly_count):
        natural_start = week_start + timedelta(weeks=index)
        natural_end = natural_start + timedelta(weeks=1)
        covered_start = max(natural_start, as_of)
        interval = DateInterval(covered_start, natural_end)
        periods.append(
            ReportPeriod(
                label=f"{interval.start.isoformat()} to {interval.last_day.isoformat()}",
                interval=interval,
                granularity=Granularity.WEEKLY,
                is_partial=covered_start > natural_start,
            )
        )
    return tuple(periods)


def monthly_periods(
    as_of: date, config: ReportingConfig = DEFAULT_REPORTING_CONFIG
) -> tuple[ReportPeriod, ...]:
    """The current calendar month plus the following months (requirements.md S7.3).

    Clipped at the as-of date on the same reasoning as the weekly view. When the as-of
    date is the first of the month the current month is complete and not marked partial.
    """
    month_start = as_of.replace(day=1)
    periods = []
    for _ in range(config.monthly_count):
        natural_end = _next_month(month_start)
        covered_start = max(month_start, as_of)
        interval = DateInterval(covered_start, natural_end)
        periods.append(
            ReportPeriod(
                label=f"{month_start.year:04d}-{month_start.month:02d}",
                interval=interval,
                granularity=Granularity.MONTHLY,
                is_partial=covered_start > month_start,
            )
        )
        month_start = natural_end
    return tuple(periods)


def reporting_periods(
    as_of: date, config: ReportingConfig = DEFAULT_REPORTING_CONFIG
) -> Mapping[Granularity, tuple[ReportPeriod, ...]]:
    """Every reporting period for a run, keyed by granularity and in display order.

    Adding a fourth view -- quarters, say -- means adding a generator and one entry here;
    neither the engine nor the renderers need to change.
    """
    return {
        Granularity.DAILY: daily_periods(as_of, config),
        Granularity.WEEKLY: weekly_periods(as_of, config),
        Granularity.MONTHLY: monthly_periods(as_of, config),
    }


def reporting_window(
    periods: Mapping[Granularity, tuple[ReportPeriod, ...]],
) -> DateInterval | None:
    """The interval spanned by every reporting period, or None if there are none.

    Lets a caller discard trades that cannot touch any reported period before doing
    per-period work.
    """
    intervals = [p.interval for view in periods.values() for p in view]
    if not intervals:
        return None
    return DateInterval(
        start=min(i.start for i in intervals),
        end=max(i.end for i in intervals),
    )


def _start_of_week(day: date, week_start: int) -> date:
    """The configured week's first day, on or before ``day``."""
    return day - timedelta(days=(day.weekday() - week_start) % 7)


def _next_month(first_of_month: date) -> date:
    """The first day of the following month."""
    if first_of_month.month == 12:
        return date(first_of_month.year + 1, 1, 1)
    return date(first_of_month.year, first_of_month.month + 1, 1)
