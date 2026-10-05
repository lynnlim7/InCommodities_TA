"""Reporting window generation (requirements.md S7, AC-09, AC-10, AC-11)."""

from __future__ import annotations

from datetime import date
from itertools import pairwise

import pytest

from app.config import ReportingConfig
from app.core import (
    DateInterval,
    Granularity,
    daily_periods,
    monthly_periods,
    reporting_periods,
    reporting_window,
    weekly_periods,
)
from tests.builders import AS_OF

pytestmark = pytest.mark.unit


class TestDailyView:
    def test_seven_consecutive_days_beginning_on_the_as_of_date(self) -> None:
        """S7.1: the as-of day is included, because the trader needs today's position."""
        periods = daily_periods(AS_OF)

        assert len(periods) == 7
        assert [p.label for p in periods] == [
            "2026-10-01",
            "2026-10-02",
            "2026-10-03",
            "2026-10-04",
            "2026-10-05",
            "2026-10-06",
            "2026-10-07",
        ]

    def test_each_day_runs_from_midnight_to_the_next_midnight(self) -> None:
        first = daily_periods(AS_OF)[0]

        assert first.interval == DateInterval(date(2026, 10, 1), date(2026, 10, 2))
        assert first.interval.hours == 24

    def test_no_day_is_partial(self) -> None:
        """S7.4: an as-of *date* is supplied, not a timestamp, so partial-day treatment
        is not invented."""
        assert not any(p.is_partial for p in daily_periods(AS_OF))

    def test_count_is_configurable(self) -> None:
        assert len(daily_periods(AS_OF, ReportingConfig(daily_count=14))) == 14

    def test_days_are_contiguous_with_no_gap_or_overlap(self) -> None:
        periods = daily_periods(AS_OF)

        for earlier, later in pairwise(periods):
            assert earlier.interval.end == later.interval.start


class TestWeeklyView:
    def test_matches_the_four_documented_intervals(self) -> None:
        """S7.2 names these exact covered periods for the assessment as-of date."""
        periods = weekly_periods(AS_OF)

        assert [(p.interval.start, p.interval.last_day) for p in periods] == [
            (date(2026, 10, 1), date(2026, 10, 4)),
            (date(2026, 10, 5), date(2026, 10, 11)),
            (date(2026, 10, 12), date(2026, 10, 18)),
            (date(2026, 10, 19), date(2026, 10, 25)),
        ]

    def test_label_shows_the_actual_covered_dates_not_a_week_number(self) -> None:
        """S7.2: a week number alone is insufficient."""
        assert weekly_periods(AS_OF)[0].label == "2026-10-01 to 2026-10-04"

    def test_only_the_current_week_is_partial(self) -> None:
        periods = weekly_periods(AS_OF)

        assert periods[0].is_partial, "1 Oct is a Thursday, so the Monday week is clipped"
        assert [p.is_partial for p in periods[1:]] == [False, False, False]

    def test_the_partial_week_excludes_history_before_the_as_of_date(self) -> None:
        """Including already-delivered days would overstate exposure the desk can act on."""
        first = weekly_periods(AS_OF)[0]

        assert first.interval.start == AS_OF
        assert first.interval.hours == 96, "Thursday to Sunday is four days"

    def test_weeks_run_monday_to_sunday_by_default(self) -> None:
        second = weekly_periods(AS_OF)[1]

        assert second.interval.start.weekday() == 0
        assert second.interval.last_day.weekday() == 6

    def test_a_monday_as_of_date_yields_no_partial_week(self) -> None:
        periods = weekly_periods(date(2026, 10, 5))

        assert not periods[0].is_partial
        assert periods[0].interval == DateInterval(date(2026, 10, 5), date(2026, 10, 12))

    def test_a_sunday_as_of_date_yields_a_one_day_partial_week(self) -> None:
        """The narrowest partial week: the last day of a Monday-start week."""
        periods = weekly_periods(date(2026, 10, 11))

        assert periods[0].is_partial
        assert periods[0].interval.days == 1

    def test_week_start_is_configurable(self) -> None:
        """A Sunday-start desk is a preference, not a different calculation."""
        periods = weekly_periods(AS_OF, ReportingConfig(week_start=6))

        assert periods[1].interval.start.weekday() == 6
        assert periods[1].interval == DateInterval(date(2026, 10, 4), date(2026, 10, 11))

    def test_weeks_are_contiguous(self) -> None:
        periods = weekly_periods(AS_OF)

        for earlier, later in pairwise(periods):
            assert earlier.interval.end == later.interval.start


class TestMonthlyView:
    def test_covers_the_current_month_plus_eleven(self) -> None:
        """S7.3: October 2026 through September 2027 for the assessment as-of date."""
        periods = monthly_periods(AS_OF)

        assert len(periods) == 12
        assert periods[0].label == "2026-10"
        assert periods[-1].label == "2027-09"

    def test_crosses_the_year_boundary(self) -> None:
        labels = [p.label for p in monthly_periods(AS_OF)]

        assert labels[2:5] == ["2026-12", "2027-01", "2027-02"]

    def test_the_current_month_is_not_partial_when_as_of_is_the_first(self) -> None:
        """S7.3: 1 October is already the month's first day, so October is complete."""
        periods = monthly_periods(AS_OF)

        assert not periods[0].is_partial
        assert periods[0].interval == DateInterval(date(2026, 10, 1), date(2026, 11, 1))

    def test_a_mid_month_as_of_date_clips_the_current_month(self) -> None:
        periods = monthly_periods(date(2026, 10, 15))

        assert periods[0].is_partial
        assert periods[0].label == "2026-10", "the month is still named, with covered dates"
        assert periods[0].interval == DateInterval(date(2026, 10, 15), date(2026, 11, 1))
        assert periods[0].interval.hours == 17 * 24
        assert not periods[1].is_partial

    def test_month_lengths_follow_the_calendar(self) -> None:
        """February 2027 has 28 days; the engine must not assume a 30-day month."""
        by_label = {p.label: p for p in monthly_periods(AS_OF)}

        assert by_label["2026-11"].interval.days == 30
        assert by_label["2026-12"].interval.days == 31
        assert by_label["2027-02"].interval.days == 28

    def test_december_rolls_into_january_of_the_next_year(self) -> None:
        periods = monthly_periods(date(2026, 12, 1), ReportingConfig(monthly_count=2))

        assert periods[1].label == "2027-01"
        assert periods[1].interval == DateInterval(date(2027, 1, 1), date(2027, 2, 1))

    def test_a_leap_february_is_handled(self) -> None:
        periods = monthly_periods(date(2028, 2, 1), ReportingConfig(monthly_count=1))

        assert periods[0].interval.days == 29

    def test_months_are_contiguous(self) -> None:
        periods = monthly_periods(AS_OF)

        for earlier, later in pairwise(periods):
            assert earlier.interval.end == later.interval.start


class TestReportingPeriods:
    def test_returns_all_three_views_in_display_order(self) -> None:
        periods = reporting_periods(AS_OF)

        assert list(periods) == [Granularity.DAILY, Granularity.WEEKLY, Granularity.MONTHLY]
        assert [len(v) for v in periods.values()] == [7, 4, 12]

    def test_generation_is_deterministic(self) -> None:
        """AC-01: repeated runs on the same inputs must produce identical periods."""
        assert reporting_periods(AS_OF) == reporting_periods(AS_OF)


class TestReportingWindow:
    def test_spans_from_the_as_of_date_to_the_last_reported_month(self) -> None:
        window = reporting_window(reporting_periods(AS_OF))

        assert window == DateInterval(date(2026, 10, 1), date(2027, 10, 1))

    def test_is_none_when_there_are_no_periods(self) -> None:
        assert reporting_window({}) is None


class TestConfigValidation:
    @pytest.mark.parametrize("field", ["daily_count", "weekly_count", "monthly_count"])
    @pytest.mark.parametrize("count", [0, -1])
    def test_rejects_non_positive_counts(self, field: str, count: int) -> None:
        with pytest.raises(ValueError, match=field):
            ReportingConfig(**{field: count})

    @pytest.mark.parametrize("week_start", [-1, 7])
    def test_rejects_out_of_range_week_start(self, week_start: int) -> None:
        with pytest.raises(ValueError, match="week_start"):
            ReportingConfig(week_start=week_start)
