"""The position engine: netting, isolation, overlap, and Average MW (AC-06 to AC-13)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.config import ReportingConfig
from app.core import (
    DateInterval,
    Direction,
    Granularity,
    Position,
    TradeBook,
    average_mw,
    calculate_views,
    net_mwh,
)
from tests.builders import AS_OF, make_trade, supplied_book

pytestmark = pytest.mark.unit

ONE_DAY_ONLY = ReportingConfig(daily_count=1, weekly_count=1, monthly_count=1)


def october() -> DateInterval:
    return DateInterval(date(2026, 10, 1), date(2026, 11, 1))


class TestNetting:
    def test_overlapping_buys_and_sells_net_algebraically(self) -> None:
        """AC-07 and S10.1: on 1 October Tokyo is +20 +15 -5 = +30 MW."""
        trades = (
            make_trade(trade_id="T001", volume_mw=20, direction=Direction.BUY),
            make_trade(trade_id="T002", volume_mw=15, direction=Direction.BUY),
            make_trade(trade_id="T003", volume_mw=5, direction=Direction.SELL),
        )
        day = DateInterval(date(2026, 10, 1), date(2026, 10, 2))

        assert net_mwh(trades, day) == Decimal(30 * 24)

    def test_an_offsetting_pair_nets_to_exactly_flat(self) -> None:
        trades = (
            make_trade(trade_id="T001", volume_mw=10, direction=Direction.BUY),
            make_trade(trade_id="T002", volume_mw=10, direction=Direction.SELL),
        )

        assert net_mwh(trades, october()) == Decimal(0)

    def test_no_trades_nets_to_zero(self) -> None:
        assert net_mwh((), october()) == Decimal(0)


class TestAreaIsolation:
    def test_trades_contribute_only_to_their_own_area(self) -> None:
        """AC-08: Tokyo trades must not affect Kansai totals."""
        book = TradeBook(
            (
                make_trade(trade_id="T001", area="Tokyo", volume_mw=30),
                make_trade(trade_id="T011", area="Kansai", volume_mw=12),
            )
        )

        rows = {r.area: r for r in calculate_views(book, AS_OF, ONE_DAY_ONLY)[Granularity.DAILY]}

        assert rows["Tokyo"].net_mwh == Decimal(30 * 24)
        assert rows["Kansai"].net_mwh == Decimal(12 * 24)

    def test_a_short_in_one_area_does_not_offset_a_long_in_another(self) -> None:
        book = TradeBook(
            (
                make_trade(trade_id="T001", area="Tokyo", volume_mw=10, direction=Direction.BUY),
                make_trade(trade_id="T002", area="Kansai", volume_mw=10, direction=Direction.SELL),
            )
        )

        rows = {r.area: r for r in calculate_views(book, AS_OF, ONE_DAY_ONLY)[Granularity.DAILY]}

        assert rows["Tokyo"].position is Position.LONG
        assert rows["Kansai"].position is Position.SHORT


class TestOverlap:
    def test_a_trade_outside_every_period_contributes_nothing(self) -> None:
        """AC-06, and the horizon pre-filter must not change this answer."""
        book = TradeBook(
            (make_trade(trade_id="T009", start=date(2030, 1, 1), end=date(2031, 1, 1)),)
        )

        view = calculate_views(book, AS_OF)[Granularity.MONTHLY]

        assert {r.net_mwh for r in view} == {Decimal(0)}
        assert {r.position for r in view} == {Position.FLAT}

    def test_only_the_intersection_contributes(self) -> None:
        """A calendar-year trade reports only its October days in the October row."""
        book = TradeBook(
            (
                make_trade(
                    trade_id="T001", volume_mw=20, start=date(2026, 1, 1), end=date(2027, 1, 1)
                ),
            )
        )

        october_row = calculate_views(book, AS_OF)[Granularity.MONTHLY].rows[0]

        assert october_row.net_mwh == Decimal(20 * 31 * 24)

    def test_the_exclusive_end_boundary_is_respected_across_views(self) -> None:
        """AC-04 and S10.5: T005 ends on 12 Oct and T004 starts on 12 Oct.

        The 12th belongs to T004 alone. If the boundary leaked, the week containing it
        would be wrong in both directions at once.
        """
        book = TradeBook(
            (
                make_trade(
                    trade_id="T005",
                    volume_mw=8,
                    direction=Direction.SELL,
                    start=date(2026, 10, 10),
                    end=date(2026, 10, 12),
                ),
                make_trade(
                    trade_id="T004",
                    volume_mw=10,
                    start=date(2026, 10, 12),
                    end=date(2026, 10, 19),
                ),
            )
        )

        daily = {
            r.period.label: r
            for r in calculate_views(book, AS_OF, ReportingConfig(daily_count=14))[
                Granularity.DAILY
            ]
        }

        assert daily["2026-10-11"].net_mwh == Decimal(-8 * 24)
        assert daily["2026-10-12"].net_mwh == Decimal(10 * 24)


class TestZeroExposure:
    def test_an_observed_area_with_no_exposure_is_shown_as_flat_not_omitted(self) -> None:
        """AC-13: a trader must be able to tell FLAT apart from missing output."""
        views = calculate_views(supplied_book(), AS_OF)
        monthly = views[Granularity.MONTHLY]

        kansai_2027_01 = next(
            r for r in monthly if r.area == "Kansai" and r.period.label == "2027-01"
        )

        assert kansai_2027_01.net_mwh == Decimal(0)
        assert kansai_2027_01.average_mw == Decimal(0)
        assert kansai_2027_01.position is Position.FLAT

    def test_every_area_appears_in_every_period(self) -> None:
        views = calculate_views(supplied_book(), AS_OF)

        for view in views:
            labels = {r.period.label for r in view}
            for label in labels:
                areas = [r.area for r in view if r.period.label == label]
                assert areas == list(views.areas), f"{label} is missing an area"

    def test_an_empty_book_produces_no_rows_rather_than_failing(self) -> None:
        views = calculate_views(TradeBook(()), AS_OF)

        assert views.areas == ()
        assert views.row_counts == {"daily": 0, "weekly": 0, "monthly": 0}


class TestAverageMw:
    def test_equals_net_mwh_over_the_periods_wall_clock_hours(self) -> None:
        """S6.3 defines the denominator as the hours in the reporting window."""
        views = calculate_views(supplied_book(), AS_OF)

        for view in views:
            for row in view:
                assert row.average_mw == average_mw(row.net_mwh, row.period.interval)

    def test_equals_the_constant_daily_mw_for_a_base_only_day(self) -> None:
        """S6.3: for daily Base-only rows the average is the constant net MW."""
        row = calculate_views(supplied_book(), AS_OF, ONE_DAY_ONLY)[Granularity.DAILY].rows[0]

        assert row.average_mw == Decimal(30)

    def test_is_time_weighted_when_exposure_changes_inside_the_period(self) -> None:
        """S10.9: a week's MWh is not the opening MW multiplied by the total hours.

        Tokyo is 30 MW from 5 to 9 October and 22 MW on the 10th and 11th once the
        weekend sell starts, giving 4,656 MWh rather than 30 x 168 = 5,040.
        """
        week = next(
            r
            for r in calculate_views(supplied_book(), AS_OF)[Granularity.WEEKLY]
            if r.area == "Tokyo" and r.period.label == "2026-10-05 to 2026-10-11"
        )

        assert week.net_mwh == Decimal(4_656)
        assert week.net_mwh != Decimal(30 * 168)
        assert week.average_mw != Decimal(30)
        assert week.average_mw == Decimal(4_656) / Decimal(168)

    def test_a_partial_week_averages_over_its_covered_hours_only(self) -> None:
        """The first week covers four days, so 2,880 MWh over 96 hours is still 30 MW."""
        week = calculate_views(supplied_book(), AS_OF)[Granularity.WEEKLY].rows[0]

        assert week.period.is_partial
        assert week.period.interval.hours == 96
        assert week.net_mwh == Decimal(2_880)
        assert week.average_mw == Decimal(30)


class TestNoRoundingInTheEngine:
    def test_repeating_averages_keep_their_precision(self) -> None:
        """S5.4: aggregation uses unrounded values; rounding is presentation-only."""
        row = next(
            r
            for r in calculate_views(supplied_book(), AS_OF)[Granularity.MONTHLY]
            if r.area == "Tokyo" and r.period.label == "2026-10"
        )

        assert row.net_mwh == Decimal(23_616), "net MWh is exact"
        assert row.average_mw != Decimal("31.74"), "the average must not arrive pre-rounded"
        assert str(row.average_mw).startswith("31.7419354838")

    def test_net_mwh_is_exact_for_fractional_volumes(self) -> None:
        """Decimal at the boundary means 0.1 MW behaves exactly, unlike binary floats."""
        book = TradeBook((make_trade(volume_mw=Decimal("0.1")),))

        row = calculate_views(book, AS_OF, ONE_DAY_ONLY)[Granularity.DAILY].rows[0]

        assert row.net_mwh == Decimal("2.4")
        assert row.average_mw == Decimal("0.1")


class TestAdditivity:
    def test_daily_rows_sum_to_the_aligned_weekly_row(self) -> None:
        """Net MWh is the additive period quantity (S6.3), so the views must agree."""
        config = ReportingConfig(daily_count=7)
        views = calculate_views(supplied_book(), date(2026, 10, 5), config)

        for area in views.areas:
            daily_total = sum(
                (r.net_mwh for r in views[Granularity.DAILY] if r.area == area), Decimal(0)
            )
            weekly = next(r for r in views[Granularity.WEEKLY] if r.area == area)
            assert daily_total == weekly.net_mwh, area

    def test_monthly_rows_sum_to_the_same_total_as_a_single_long_window(self) -> None:
        book = supplied_book()
        monthly = calculate_views(book, AS_OF)[Granularity.MONTHLY]
        whole_year = DateInterval(date(2026, 10, 1), date(2027, 10, 1))

        for area in book.observed_areas:
            trades = tuple(t for t in book if t.area == area)
            month_total = sum((r.net_mwh for r in monthly if r.area == area), Decimal(0))
            assert month_total == net_mwh(trades, whole_year), area


class TestRowOrdering:
    def test_rows_are_period_major_then_area(self) -> None:
        """S9 presents each period as a contiguous block, which is how a trader scans."""
        view = calculate_views(supplied_book(), AS_OF)[Granularity.DAILY]

        assert [(r.period.label, r.area) for r in view.rows[:4]] == [
            ("2026-10-01", "Tokyo"),
            ("2026-10-01", "Kansai"),
            ("2026-10-02", "Tokyo"),
            ("2026-10-02", "Kansai"),
        ]

    def test_periods_are_chronological(self) -> None:
        for view in calculate_views(supplied_book(), AS_OF):
            starts = [r.period.start for r in view]
            assert starts == sorted(starts)

    def test_repeated_runs_are_identical(self) -> None:
        """AC-01: the trade book plus the as-of value fully determine the result."""
        first = calculate_views(supplied_book(), AS_OF)
        second = calculate_views(supplied_book(), AS_OF)

        assert first == second


class TestHorizonPrefilter:
    def test_discarding_far_trades_does_not_change_any_result(self) -> None:
        """The pre-filter is an optimisation, so adding an out-of-window trade to the book
        must leave every reported figure untouched."""
        book = supplied_book()
        with_far_trade = TradeBook(
            (
                *book.trades,
                make_trade(trade_id="T999", start=date(2035, 1, 1), end=date(2036, 1, 1)),
            )
        )

        assert [
            (r.area, r.period.label, r.net_mwh)
            for v in calculate_views(with_far_trade, AS_OF)
            for r in v
        ] == [(r.area, r.period.label, r.net_mwh) for v in calculate_views(book, AS_OF) for r in v]
