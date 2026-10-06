"""Position calculation -- the behaviour the desk actually depends on.

Each test is one business scenario, written out in full so the trade book and
the expected arithmetic can both be read without leaving the test.

Two conventions run through all of them:

* Volume is quoted in MW and the reported position stays in MW. Delivery hours
  are only the weight, so the engine divides MW-hours by the reporting
  period's own profile hours. A trade covering the whole period therefore
  reports its own MW, not its MWh.
* Expected values stay in ``Decimal`` and are written as the unevaluated
  formula. ``10 * 336 / 744`` does not terminate in decimal, and writing it as
  a float approximation would both hide the business formula and weaken the
  assertion.
"""

from decimal import Decimal

import pytest

from app.core.calculations import calculate_positions, contributing_trades
from app.core.errors import UnsupportedAreaError
from app.core.models import BuySell
from app.core.profiles import ContinuousProfile, HourlyWindowProfile, ProfileRegistry
from tests.helpers import book, make_trade, position_for, reporting

pytestmark = pytest.mark.unit

# October 2026 has 31 days: 744 continuous hours, and 22 weekdays.
OCTOBER = reporting("Oct-26", "2026-10-01", "2026-11-01")
TOKYO = frozenset({"Tokyo"})

BASE_ONLY = ProfileRegistry(profiles={"Base": ContinuousProfile()})
PEAK = HourlyWindowProfile(
    start_hour=8,
    end_hour=20,
    weekdays=frozenset({0, 1, 2, 3, 4}),
)


def october_base(positions, area="Tokyo"):
    return position_for(
        positions, area=area, load_profile="Base", period=OCTOBER
    ).net_position_mw


def test_a_buy_covering_the_whole_period_reports_its_full_volume_long():
    """Buy 10 MW Base, Oct 1 -> Nov 1, reported over Oct 1 -> Nov 1 = +10 MW."""
    positions = calculate_positions(
        trade_book=book(
            make_trade(buy_sell=BuySell.BUY, volume_mw="10",
                       start="2026-10-01", end="2026-11-01")
        ),
        periods=(OCTOBER,),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
    )

    assert october_base(positions) == Decimal("10")


def test_a_sell_covering_the_whole_period_reports_its_full_volume_short():
    """Sell 10 MW Base, Oct 1 -> Nov 1, reported over the same = -10 MW."""
    positions = calculate_positions(
        trade_book=book(
            make_trade(buy_sell=BuySell.SELL, volume_mw="10",
                       start="2026-10-01", end="2026-11-01")
        ),
        periods=(OCTOBER,),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
    )

    assert october_base(positions) == Decimal("-10")


def test_a_trade_covering_part_of_the_period_is_time_weighted_down():
    """Buy 10 MW over Oct 1 -> Oct 15 is not a 10 MW October position.

    The trade delivers 14 x 24 = 336 of October's 744 Base hours, so the
    time-weighted October position is 10 x 336 / 744 MW.
    """
    positions = calculate_positions(
        trade_book=book(make_trade(volume_mw="10", start="2026-10-01", end="2026-10-15")),
        periods=(OCTOBER,),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
    )

    assert october_base(positions) == Decimal("10") * Decimal("336") / Decimal("744")


def test_adjacent_trades_are_time_weighted_not_added():
    """Two back-to-back trades at different volumes do not sum to 15 MW.

    Trade A delivers 10 MW for Oct 1 -> Oct 15 (336 hours) and trade B
    delivers 5 MW for Oct 15 -> Nov 1 (408 hours). They are adjacent, never
    concurrent, so the October position is the hour-weighted average of the
    two -- (10 x 336 + 5 x 408) / 744 -- not 15 MW.

    This is the test that protects the aggregation semantics: a naive sum of
    volumes would report more than twice the real exposure here.
    """
    positions = calculate_positions(
        trade_book=book(
            make_trade(trade_id="A", volume_mw="10", start="2026-10-01", end="2026-10-15"),
            make_trade(trade_id="B", volume_mw="5", start="2026-10-15", end="2026-11-01"),
        ),
        periods=(OCTOBER,),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
    )

    expected = (
        Decimal("10") * Decimal("336") + Decimal("5") * Decimal("408")
    ) / Decimal("744")
    assert october_base(positions) == expected
    assert october_base(positions) != Decimal("15")


def test_an_overlapping_buy_and_sell_net_over_their_shared_hours():
    """A Buy and a partially overlapping Sell net by signed MW-hours.

    Buy 10 MW for all 744 hours, Sell 5 MW for the last 408, giving
    (10 x 744 - 5 x 408) / 744 MW -- still long, but less long over the half
    of the month the sell covers.
    """
    positions = calculate_positions(
        trade_book=book(
            make_trade(trade_id="A", buy_sell=BuySell.BUY, volume_mw="10",
                       start="2026-10-01", end="2026-11-01"),
            make_trade(trade_id="B", buy_sell=BuySell.SELL, volume_mw="5",
                       start="2026-10-15", end="2026-11-01"),
        ),
        periods=(OCTOBER,),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
    )

    expected = (
        Decimal("10") * Decimal("744") - Decimal("5") * Decimal("408")
    ) / Decimal("744")
    assert october_base(positions) == expected


def test_a_trade_delivered_before_the_period_contributes_nothing():
    """A September trade is irrelevant to October, and reports as flat.

    A flat row is still emitted, so "no exposure" is distinguishable from
    "area missing from the report".
    """
    positions = calculate_positions(
        trade_book=book(make_trade(volume_mw="10", start="2026-09-01", end="2026-10-01")),
        periods=(OCTOBER,),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
    )

    assert october_base(positions) == Decimal("0")


def test_base_and_peak_are_reported_as_separate_positions():
    """Base and Peak are different products and are never collapsed.

    The same 10 MW notional means a different thing on each profile, so each
    is divided by its own profile hours in October: Base by 744, Peak by
    22 weekdays x 12 = 264.
    """
    positions = calculate_positions(
        trade_book=book(
            make_trade(trade_id="BASE", load_profile="Base", volume_mw="10",
                       start="2026-10-01", end="2026-11-01"),
            make_trade(trade_id="PEAK", load_profile="Peak", buy_sell=BuySell.SELL,
                       volume_mw="8", start="2026-10-01", end="2026-11-01"),
        ),
        periods=(OCTOBER,),
        profiles=ProfileRegistry(profiles={"Base": ContinuousProfile(), "Peak": PEAK}),
        supported_areas=TOKYO,
    )

    base = position_for(positions, area="Tokyo", load_profile="Base", period=OCTOBER)
    peak = position_for(positions, area="Tokyo", load_profile="Peak", period=OCTOBER)

    assert base.net_position_mw == Decimal("10")
    assert peak.net_position_mw == Decimal("-8")


def test_a_period_with_no_profile_hours_reports_flat_rather_than_failing():
    """A daily Peak row on a Saturday has no hours to weight against.

    Saturday is not a configured Peak delivery day, so the denominator is
    zero. The application reports that day flat rather than dividing by zero
    or omitting the row: the trader still needs to see that Peak Saturday
    carries no exposure.
    """
    saturday = reporting("2026-10-10", "2026-10-10", "2026-10-11")

    positions = calculate_positions(
        trade_book=book(
            make_trade(load_profile="Peak", volume_mw="10",
                       start="2026-10-01", end="2026-11-01")
        ),
        periods=(saturday,),
        profiles=ProfileRegistry(profiles={"Peak": PEAK}),
        supported_areas=TOKYO,
    )

    peak = position_for(positions, area="Tokyo", load_profile="Peak", period=saturday)
    assert peak.net_position_mw == Decimal("0")


def test_areas_are_reported_separately_and_never_netted_against_each_other():
    """Tokyo and Kansai are different delivery points.

    A long in Tokyo does not offset a short in Kansai -- there is no transmission
    assumption in this tool -- so the two never appear in the same row.
    """
    positions = calculate_positions(
        trade_book=book(
            make_trade(trade_id="TK", area="Tokyo", buy_sell=BuySell.BUY, volume_mw="10"),
            make_trade(trade_id="KS", area="Kansai", buy_sell=BuySell.SELL, volume_mw="4"),
        ),
        periods=(OCTOBER,),
        profiles=BASE_ONLY,
        supported_areas=frozenset({"Tokyo", "Kansai"}),
    )

    assert october_base(positions, area="Tokyo") == Decimal("10")
    assert october_base(positions, area="Kansai") == Decimal("-4")


def test_each_reporting_period_is_weighted_independently():
    """One trade spanning two months reports against each month's own hours.

    Buy 10 MW for Oct 1 -> Nov 16 is a full 10 MW for October (744 of 744
    hours) and a part-month 10 x 360 / 720 for November (15 of 30 days).
    """
    november = reporting("Nov-26", "2026-11-01", "2026-12-01")

    positions = calculate_positions(
        trade_book=book(make_trade(volume_mw="10", start="2026-10-01", end="2026-11-16")),
        periods=(OCTOBER, november),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
    )

    assert october_base(positions) == Decimal("10")
    assert position_for(
        positions, area="Tokyo", load_profile="Base", period=november
    ).net_position_mw == Decimal("10") * Decimal("360") / Decimal("720")


def test_a_trade_in_an_unsupported_area_fails_the_run():
    """Exposure must never silently vanish from the report.

    A mistyped area ("Toyko") is not a small reporting inaccuracy: the row it
    belongs to is not emitted at all, so 10 MW of real exposure disappears and
    Tokyo reads flat. A report that looks complete while omitting a trade can
    imply the wrong hedge, so the run fails instead.

    This mirrors how the engine already treats an unregistered load profile.
    Area and profile are both reference data the book is validated against,
    and neither is guessed at.
    """
    with pytest.raises(UnsupportedAreaError):
        calculate_positions(
            trade_book=book(make_trade(area="Toyko", volume_mw="10")),
            periods=(OCTOBER,),
            profiles=BASE_ONLY,
            supported_areas=TOKYO,
        )


# --- Drill-down: which trades produced an aggregated position -----------------


def test_contributing_trades_returns_only_the_requested_area_and_profile():
    """The drill-down answers for one position row, not for the whole book."""
    positions_book = book(
        make_trade(trade_id="TK-BASE", area="Tokyo", load_profile="Base"),
        make_trade(trade_id="TK-PEAK", area="Tokyo", load_profile="Peak"),
        make_trade(trade_id="KS-BASE", area="Kansai", load_profile="Base"),
    )

    contributions = contributing_trades(
        trade_book=positions_book,
        area="Tokyo",
        load_profile="Base",
        period=OCTOBER,
        profiles=ProfileRegistry(profiles={"Base": ContinuousProfile(), "Peak": PEAK}),
    )

    assert [c.trade.trade_id for c in contributions] == ["TK-BASE"]


def test_contributing_trades_report_the_hours_that_explain_the_aggregate():
    """The applicable hours are what make the position non-additive.

    Two adjacent 10 MW and 5 MW trades do not make a 15 MW October position;
    they make 336 and 408 hours of it respectively. Reporting the hours is the
    only honest way for a drill-down to show contractual MW without implying
    they can be summed.
    """
    contributions = contributing_trades(
        trade_book=book(
            make_trade(trade_id="A", volume_mw="10", start="2026-10-01", end="2026-10-15"),
            make_trade(trade_id="B", volume_mw="5", start="2026-10-15", end="2026-11-01"),
        ),
        area="Tokyo",
        load_profile="Base",
        period=OCTOBER,
        profiles=BASE_ONLY,
    )

    assert [(c.trade.trade_id, c.applicable_hours) for c in contributions] == [
        ("A", Decimal("336")),
        ("B", Decimal("408")),
    ]


def test_contributing_trades_excludes_trades_with_no_applicable_hours():
    """A trade must both overlap the period and deliver hours inside it.

    This is the same two-part rule the engine applies, so the drill-down can
    never show a trade that did not move the number: the September trade does
    not overlap October at all, and the Peak trade overlaps a Saturday on
    which Peak does not deliver.
    """
    saturday = reporting("2026-10-10", "2026-10-10", "2026-10-11")

    assert (
        contributing_trades(
            trade_book=book(make_trade(start="2026-09-01", end="2026-10-01")),
            area="Tokyo",
            load_profile="Base",
            period=OCTOBER,
            profiles=BASE_ONLY,
        )
        == ()
    )
    assert (
        contributing_trades(
            trade_book=book(make_trade(load_profile="Peak")),
            area="Tokyo",
            load_profile="Peak",
            period=saturday,
            profiles=ProfileRegistry(profiles={"Peak": PEAK}),
        )
        == ()
    )
