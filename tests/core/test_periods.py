"""Reporting-period conventions.

These tests protect the calendar conventions a trader reads off the report,
through the public generators only. ``_shift_month`` is an implementation
detail of ``monthly_periods`` and is covered by the year-boundary case.

All dates are plain JST calendar dates: Japan has no daylight saving, so a
delivery day is always 24 hours and no timezone arithmetic is performed.
"""

from datetime import date
from itertools import pairwise

import pytest

from app.core.periods import daily_periods, monthly_periods, weekly_periods
from tests.builders import delivery

pytestmark = pytest.mark.unit

# 1 October 2026 is a Thursday; 5 October 2026 is the following Monday.
THURSDAY = date(2026, 10, 1)
MONDAY = date(2026, 10, 5)


def test_daily_periods_are_seven_forward_looking_single_days():
    periods = daily_periods(as_of=THURSDAY)

    assert len(periods) == 7
    assert periods[0].delivery == delivery("2026-10-01", "2026-10-02")
    assert periods[6].delivery == delivery("2026-10-07", "2026-10-08")


def test_daily_periods_are_contiguous_and_do_not_overlap():
    periods = daily_periods(as_of=THURSDAY)

    for earlier, later in pairwise(periods):
        assert earlier.delivery.end == later.delivery.start
        assert earlier.delivery.overlap(later.delivery) is False


def test_first_weekly_period_is_clipped_to_the_remainder_of_the_current_week():
    """From Thursday the current week is already part-delivered.

    The desk can only still trade Thursday to Sunday, so the first period is
    [Oct 1, Oct 5) and the second is the first whole Monday-Sunday week.
    """
    periods = weekly_periods(as_of=THURSDAY)

    assert periods[0].delivery == delivery("2026-10-01", "2026-10-05")
    assert periods[1].delivery == delivery("2026-10-05", "2026-10-12")


def test_weekly_periods_from_a_monday_start_with_a_whole_week():
    periods = weekly_periods(as_of=MONDAY)

    assert periods[0].delivery == delivery("2026-10-05", "2026-10-12")
    assert periods[1].delivery == delivery("2026-10-12", "2026-10-19")


def test_weekly_periods_are_contiguous_and_do_not_overlap():
    periods = weekly_periods(as_of=THURSDAY)

    assert len(periods) == 4
    for earlier, later in pairwise(periods):
        assert earlier.delivery.end == later.delivery.start
        assert earlier.delivery.overlap(later.delivery) is False


def test_monthly_periods_run_from_first_to_first():
    periods = monthly_periods(as_of=THURSDAY, count=2)

    assert [period.label for period in periods] == ["Oct-26", "Nov-26"]
    assert periods[0].delivery == delivery("2026-10-01", "2026-11-01")
    assert periods[1].delivery == delivery("2026-11-01", "2026-12-01")


def test_monthly_periods_cross_the_year_boundary():
    periods = monthly_periods(as_of=date(2026, 12, 1), count=2)

    assert [period.label for period in periods] == ["Dec-26", "Jan-27"]
    assert periods[0].delivery == delivery("2026-12-01", "2027-01-01")
    assert periods[1].delivery == delivery("2027-01-01", "2027-02-01")


def test_first_monthly_period_is_clipped_to_remain_forward_looking():
    """Mid-month, the already-delivered part of the month is excluded.

    The period keeps its calendar label (Oct-26) but its delivery interval
    starts at the as-of date, so no historical hours enter the position.
    """
    periods = monthly_periods(as_of=date(2026, 10, 15), count=2)

    assert periods[0].label == "Oct-26"
    assert periods[0].delivery == delivery("2026-10-15", "2026-11-01")
    assert periods[1].delivery == delivery("2026-11-01", "2026-12-01")
