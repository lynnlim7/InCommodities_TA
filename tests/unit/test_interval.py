"""Half-open interval semantics: the inclusive start / exclusive end rule (AC-04)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core import DateInterval, InvalidIntervalError

pytestmark = pytest.mark.unit


def test_rejects_inverted_interval() -> None:
    with pytest.raises(InvalidIntervalError):
        DateInterval(date(2026, 10, 2), date(2026, 10, 1))


def test_rejects_empty_interval() -> None:
    """start == end delivers nothing, so it is not a valid trade or reporting period."""
    with pytest.raises(InvalidIntervalError) as exc:
        DateInterval(date(2026, 10, 1), date(2026, 10, 1))

    assert "start < end" in str(exc.value)


def test_days_and_hours_count_whole_delivery_days() -> None:
    october = DateInterval(date(2026, 10, 1), date(2026, 11, 1))

    assert october.days == 31
    assert october.hours == Decimal(744)


def test_last_day_is_the_day_before_the_exclusive_end() -> None:
    """A weekend product booked as [10 Oct, 12 Oct) delivers on 10 and 11 October."""
    weekend = DateInterval(date(2026, 10, 10), date(2026, 10, 12))

    assert weekend.days == 2
    assert weekend.last_day == date(2026, 10, 11)


class TestIntersection:
    def test_identical_intervals_overlap_completely(self) -> None:
        october = DateInterval(date(2026, 10, 1), date(2026, 11, 1))

        assert october.intersection(october) == october

    def test_nested_interval_yields_the_inner_interval(self) -> None:
        october = DateInterval(date(2026, 10, 1), date(2026, 11, 1))
        week = DateInterval(date(2026, 10, 12), date(2026, 10, 19))

        assert october.intersection(week) == week
        assert week.intersection(october) == week

    def test_partial_overlap_yields_only_the_shared_days(self) -> None:
        q4 = DateInterval(date(2026, 10, 1), date(2027, 1, 1))
        calendar_2026 = DateInterval(date(2026, 1, 1), date(2027, 1, 1))

        assert q4.intersection(calendar_2026) == q4

    def test_disjoint_intervals_do_not_overlap(self) -> None:
        october = DateInterval(date(2026, 10, 1), date(2026, 11, 1))
        december = DateInterval(date(2026, 12, 1), date(2027, 1, 1))

        assert october.intersection(december) is None

    def test_abutting_intervals_do_not_overlap(self) -> None:
        """S10.5: T005 ends on 12 October and T004 starts on 12 October.

        The exclusive end must not touch the inclusive start, or that day would be
        double counted across both trades.
        """
        ends_on_12th = DateInterval(date(2026, 10, 10), date(2026, 10, 12))
        starts_on_12th = DateInterval(date(2026, 10, 12), date(2026, 10, 19))

        assert ends_on_12th.intersection(starts_on_12th) is None
        assert starts_on_12th.intersection(ends_on_12th) is None

    def test_single_shared_day_overlaps(self) -> None:
        a = DateInterval(date(2026, 10, 10), date(2026, 10, 12))
        b = DateInterval(date(2026, 10, 11), date(2026, 10, 19))

        overlap = a.intersection(b)

        assert overlap == DateInterval(date(2026, 10, 11), date(2026, 10, 12))
        assert overlap is not None and overlap.days == 1

    def test_intersection_is_commutative(self) -> None:
        a = DateInterval(date(2026, 10, 1), date(2026, 10, 20))
        b = DateInterval(date(2026, 10, 15), date(2026, 11, 5))

        assert a.intersection(b) == b.intersection(a)
