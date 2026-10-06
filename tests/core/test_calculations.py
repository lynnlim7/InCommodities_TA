"""Position calculation -- the behaviour the desk actually depends on.

Each test is one business scenario, written out in full so the trade book and
the expected arithmetic can both be read without leaving the test.

Three conventions run through all of them:

* Every trade lands on its area's hourly net MW curve, and every reported
  number is read off that curve. Net MWh is the curve summed over the
  period's hours; net MW is that energy divided by the period's hours, so a
  trade covering the whole period reports its own MW.
* Load profiles net into the hours they share. The headline position is
  every hour of the period (the Base shape); the Peak block repeats it over
  Peak hours only, which is where Base and Peak trades meet.
* Expected values stay in ``Decimal`` and are written as the unevaluated
  formula. ``10 * 336 / 744`` does not terminate in decimal, and writing it as
  a float approximation would both hide the business formula and weaken the
  assertion.
"""

from decimal import Decimal

import pytest

from app.core.calculations import calculate_positions, contributing_trades
from app.core.errors import (
    UnsupportedAreaError,
    UnsupportedProfileError,
    UnsupportedTradeTypeError,
)
from app.core.models import BuySell
from app.core.profiles import (
    ContinuousProfile,
    HourlyWindowProfile,
    ProfileRegistry,
)
from tests.helpers import book, make_trade, position_for, reporting

pytestmark = pytest.mark.unit

# October 2026 has 31 days: 744 hours, of which 22 weekdays x 12 = 264 are
# Peak hours.
OCTOBER = reporting("Oct-26", "2026-10-01", "2026-11-01")
TOKYO = frozenset({"Tokyo"})
FUTURES = frozenset({"Futures"})

BASE_ONLY = ProfileRegistry(profiles={"Base": ContinuousProfile()})
PEAK = HourlyWindowProfile(
    start_hour=8,
    end_hour=20,
    weekdays=frozenset({0, 1, 2, 3, 4}),
)
BASE_PEAK = ProfileRegistry(
    profiles={
        "Base": ContinuousProfile(),
        "Peak": PEAK,
    }
)
BLOCKS = ("Peak",)


def october(positions, area="Tokyo"):
    return position_for(positions, area=area, period=OCTOBER)


def october_mw(positions, area="Tokyo"):
    return october(positions, area).net_position_mw


def october_mwh(positions, area="Tokyo"):
    return october(positions, area).net_position_mwh


def test_a_buy_covering_the_whole_period_reports_its_full_volume_long():
    """Buy 10 MW Base, Oct 1 -> Nov 1, reported over the same = +10 MW, 7,440 MWh.

    This is also where the two reported units are pinned to each other: the
    net MWh divided by the period's 744 hours is exactly the reported net MW,
    because both are read off the same curve.
    """
    positions = calculate_positions(
        trade_book=book(
            make_trade(buy_sell=BuySell.BUY, volume_mw="10",
                       start="2026-10-01", end="2026-11-01")
        ),
        periods=(OCTOBER,),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
        supported_trade_types=FUTURES,
    )

    assert october_mw(positions) == Decimal("10")
    assert october_mwh(positions) == Decimal("10") * Decimal("744")
    assert october_mwh(positions) / Decimal("744") == october_mw(positions)


def test_a_sell_covering_the_whole_period_reports_its_full_volume_short():
    """Sell 10 MW Base, Oct 1 -> Nov 1 = -10 MW and -7,440 MWh.

    Direction is carried by both units, so a short never reads as positive
    energy owed to the desk.
    """
    positions = calculate_positions(
        trade_book=book(
            make_trade(buy_sell=BuySell.SELL, volume_mw="10",
                       start="2026-10-01", end="2026-11-01")
        ),
        periods=(OCTOBER,),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
        supported_trade_types=FUTURES,
    )

    assert october_mw(positions) == Decimal("-10")
    assert october_mwh(positions) == Decimal("-7440")


def test_a_trade_covering_part_of_the_period_is_time_weighted_down():
    """Buy 10 MW over Oct 1 -> Oct 15 is not a 10 MW October position.

    The trade delivers 14 x 24 = 336 of October's 744 hours, so the October
    average is 10 x 336 / 744 MW. The hourly range shows the rest: 10 MW for
    the first half of the month and nothing after it.
    """
    positions = calculate_positions(
        trade_book=book(make_trade(volume_mw="10", start="2026-10-01", end="2026-10-15")),
        periods=(OCTOBER,),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
        supported_trade_types=FUTURES,
    )

    assert october_mw(positions) == Decimal("10") * Decimal("336") / Decimal("744")
    assert october(positions).exposure.min_mw == Decimal("0")
    assert october(positions).exposure.max_mw == Decimal("10")


def test_a_part_period_trade_reports_the_energy_it_actually_delivers():
    """The same Oct 1 -> Oct 15 buy is 10 x 336 = 3,360 MWh of October.

    MWh is where the part-month trade is read at face value: the desk is
    committed to that energy outright, whereas the MW figure dilutes it over
    the hours of October the trade does not cover. The two units are
    deliberately both on the screen for this reason.
    """
    positions = calculate_positions(
        trade_book=book(make_trade(volume_mw="10", start="2026-10-01", end="2026-10-15")),
        periods=(OCTOBER,),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
        supported_trade_types=FUTURES,
    )

    assert october_mwh(positions) == Decimal("10") * Decimal("336")


def test_adjacent_trades_are_time_weighted_not_added():
    """Two back-to-back trades at different volumes do not sum to 15 MW.

    Trade A delivers 10 MW for Oct 1 -> Oct 15 (336 hours) and trade B
    delivers 5 MW for Oct 15 -> Nov 1 (408 hours). They are adjacent, never
    concurrent, so the October position is the hour-weighted average of the
    two -- (10 x 336 + 5 x 408) / 744 -- not 15 MW. No single hour is ever
    above 10 MW.

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
        supported_trade_types=FUTURES,
    )

    expected = (
        Decimal("10") * Decimal("336") + Decimal("5") * Decimal("408")
    ) / Decimal("744")
    assert october_mw(positions) == expected
    assert october_mw(positions) != Decimal("15")
    assert october(positions).exposure.max_mw == Decimal("10")

    # Energy, unlike MW, is cumulative: the two trades' MWh do add.
    assert october_mwh(positions) == (
        Decimal("10") * Decimal("336") + Decimal("5") * Decimal("408")
    )


def test_an_overlapping_buy_and_sell_net_over_their_shared_hours():
    """A Buy and a partially overlapping Sell net hour by hour.

    Buy 10 MW for all 744 hours, Sell 5 MW for the last 408, giving
    (10 x 744 - 5 x 408) / 744 MW -- still long, but only 5 MW long over the
    half of the month the sell covers.
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
        supported_trade_types=FUTURES,
    )

    expected = (
        Decimal("10") * Decimal("744") - Decimal("5") * Decimal("408")
    ) / Decimal("744")
    assert october_mw(positions) == expected
    assert october(positions).exposure.min_mw == Decimal("5")
    assert october(positions).exposure.max_mw == Decimal("10")


def test_an_average_long_can_hide_short_hours_and_the_range_shows_them():
    """Buy 10 MW for the week, Sell 20 MW for its weekend.

    The week averages (10 x 168 - 20 x 48) / 168 = +4.29 MW, which alone
    reads as comfortably long. But the desk is 10 MW short in every weekend
    hour. The hourly range is what tells the trader: its low end is -10.
    """
    week = reporting("Week 41", "2026-10-05", "2026-10-12")

    positions = calculate_positions(
        trade_book=book(
            make_trade(trade_id="WEEK", buy_sell=BuySell.BUY, volume_mw="10",
                       start="2026-10-05", end="2026-10-12"),
            make_trade(trade_id="WKND", buy_sell=BuySell.SELL, volume_mw="20",
                       start="2026-10-10", end="2026-10-12"),
        ),
        periods=(week,),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
        supported_trade_types=FUTURES,
    )

    exposure = position_for(positions, area="Tokyo", period=week).exposure

    assert exposure.net_mw == (
        Decimal("10") * Decimal("168") - Decimal("20") * Decimal("48")
    ) / Decimal("168")
    assert exposure.net_mw > 0
    assert exposure.min_mw == Decimal("-10")
    assert exposure.max_mw == Decimal("10")


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
        supported_trade_types=FUTURES,
    )

    assert october_mw(positions) == Decimal("0")
    assert october_mwh(positions) == Decimal("0")


def test_base_and_peak_net_into_the_hours_they_share():
    """Buy 10 MW Base and Sell 8 MW Peak for October.

    The two trades share October's 264 peak hours. There the desk is
    10 - 8 = +2 MW, which the Peak block reports; in the other 480 hours it
    is +10 MW. The Base figure is the energy of both trades over all 744
    hours, and its hourly range shows the two levels.
    """
    positions = calculate_positions(
        trade_book=book(
            make_trade(trade_id="BASE", load_profile="Base", volume_mw="10",
                       start="2026-10-01", end="2026-11-01"),
            make_trade(trade_id="PEAK", load_profile="Peak", buy_sell=BuySell.SELL,
                       volume_mw="8", start="2026-10-01", end="2026-11-01"),
        ),
        periods=(OCTOBER,),
        profiles=BASE_PEAK,
        supported_areas=TOKYO,
        supported_trade_types=FUTURES,
        blocks=BLOCKS,
    )

    position = october(positions)

    assert position.block("Peak").net_mw == Decimal("2")
    assert position.block("Peak").hours == 264

    assert position.net_position_mwh == (
        Decimal("10") * Decimal("744") - Decimal("8") * Decimal("264")
    )
    assert position.exposure.min_mw == Decimal("2")
    assert position.exposure.max_mw == Decimal("10")


def test_a_base_long_and_an_equal_peak_short_are_flat_in_peak_hours():
    """Long 10 Base, short 10 Peak: hedged in the peak, long 10 outside it.

    Reported as two separate per-product positions this would read +10 and
    -10; on the curve the Peak block is flat and the Base figure is long by
    the hours outside the peak, which is what the desk actually holds.
    """
    positions = calculate_positions(
        trade_book=book(
            make_trade(trade_id="BASE", load_profile="Base", volume_mw="10"),
            make_trade(trade_id="PEAK", load_profile="Peak",
                       buy_sell=BuySell.SELL, volume_mw="10"),
        ),
        periods=(OCTOBER,),
        profiles=BASE_PEAK,
        supported_areas=TOKYO,
        supported_trade_types=FUTURES,
        blocks=BLOCKS,
    )

    position = october(positions)

    assert position.block("Peak").net_mw == Decimal("0")
    assert position.net_position_mw == (
        Decimal("10") * Decimal("744") - Decimal("10") * Decimal("264")
    ) / Decimal("744")
    assert position.exposure.max_mw == Decimal("10")


def test_a_block_with_no_hours_in_the_period_reports_no_hours():
    """A Saturday has no Peak hours to average over.

    Saturday is not a configured Peak delivery day, so the Peak block holds
    zero hours. It reports that rather than dividing by zero or omitting the
    row, while the Base figure still covers all 24 hours.
    """
    saturday = reporting("2026-10-10", "2026-10-10", "2026-10-11")

    positions = calculate_positions(
        trade_book=book(
            make_trade(load_profile="Base", volume_mw="10",
                       start="2026-10-01", end="2026-11-01")
        ),
        periods=(saturday,),
        profiles=BASE_PEAK,
        supported_areas=TOKYO,
        supported_trade_types=FUTURES,
        blocks=BLOCKS,
    )

    position = position_for(positions, area="Tokyo", period=saturday)

    assert position.block("Peak").hours == 0
    assert position.block("Peak").net_mw == Decimal("0")
    assert position.exposure.hours == 24
    assert position.net_position_mw == Decimal("10")


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
        supported_trade_types=FUTURES,
    )

    assert october_mw(positions, area="Tokyo") == Decimal("10")
    assert october_mw(positions, area="Kansai") == Decimal("-4")


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
        supported_trade_types=FUTURES,
    )

    assert october_mw(positions) == Decimal("10")
    assert position_for(
        positions, area="Tokyo", period=november
    ).net_position_mw == Decimal("10") * Decimal("360") / Decimal("720")


def test_overlapping_reporting_periods_are_read_off_the_same_curve():
    """A day, the week it sits in and the month agree with each other.

    The views overlap -- 5 Oct is in the daily view, the 5-11 Oct week and
    October -- and each is a different read of one curve, so the daily
    energy adds up to the week's.
    """
    days = tuple(
        reporting(f"2026-10-{day:02d}", f"2026-10-{day:02d}", f"2026-10-{day + 1:02d}")
        for day in range(5, 12)
    )
    week = reporting("Week 41", "2026-10-05", "2026-10-12")

    positions = calculate_positions(
        trade_book=book(
            make_trade(trade_id="A", volume_mw="10"),
            make_trade(trade_id="B", buy_sell=BuySell.SELL, volume_mw="8",
                       start="2026-10-10", end="2026-10-12"),
        ),
        periods=(*days, week, OCTOBER),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
        supported_trade_types=FUTURES,
    )

    daily_mwh = sum(
        (position_for(positions, area="Tokyo", period=day).net_position_mwh
         for day in days),
        start=Decimal("0"),
    )

    assert daily_mwh == position_for(
        positions, area="Tokyo", period=week
    ).net_position_mwh


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
            supported_trade_types=FUTURES,
        )


def test_a_trade_with_an_unsupported_trade_type_fails_the_run():
    """A "Swap" is not a configured trade type, so the book is rejected.

    Trade type does not change the MW a trade delivers, but it is still
    reference data the book is validated against, exactly like area and
    profile. Accepting an unknown type would let a trade the desk has not
    agreed how to book flow silently into the position.
    """
    with pytest.raises(UnsupportedTradeTypeError):
        calculate_positions(
            trade_book=book(make_trade(trade_type="Swap", volume_mw="10")),
            periods=(OCTOBER,),
            profiles=BASE_ONLY,
            supported_areas=TOKYO,
            supported_trade_types=FUTURES,
        )


def test_every_configured_trade_type_contributes_the_same_way():
    """A Future and an OTC Forward of the same shape net like any two trades.

    Both are configured, so both are accepted, and trade type does not
    change the arithmetic: Buy 10 MW Futures and Sell 4 MW OTC Forwards for
    October is +6 MW.
    """
    positions = calculate_positions(
        trade_book=book(
            make_trade(trade_id="FUT", trade_type="Futures", volume_mw="10"),
            make_trade(trade_id="OTC", trade_type="OTC Forwards",
                       buy_sell=BuySell.SELL, volume_mw="4"),
        ),
        periods=(OCTOBER,),
        profiles=BASE_ONLY,
        supported_areas=TOKYO,
        supported_trade_types=frozenset({"Futures", "OTC Forwards"}),
    )

    assert october_mw(positions) == Decimal("6")


def test_an_unknown_profile_fails_the_run_even_outside_the_horizon():
    """A trade is validated before it is clipped to the reporting horizon.

    A 2025 trade on an unknown profile delivers nothing in October, but it is
    still a bad reference in the book, and the book is accepted whole or not
    at all.
    """
    with pytest.raises(UnsupportedProfileError):
        calculate_positions(
            trade_book=book(make_trade(load_profile="Shoulder",
                                       start="2025-01-01", end="2025-02-01")),
            periods=(OCTOBER,),
            profiles=BASE_ONLY,
            supported_areas=TOKYO,
            supported_trade_types=FUTURES,
        )


# --- Drill-down: which trades produced an aggregated position -----------------


def test_contributing_trades_returns_every_profile_in_the_requested_area():
    """The drill-down answers for one area's row, across all its profiles.

    Every profile lands on the same curve the row is read from, so a Peak
    trade is part of the Tokyo position just as a Base trade is. Kansai is
    not.
    """
    positions_book = book(
        make_trade(trade_id="TK-BASE", area="Tokyo", load_profile="Base"),
        make_trade(trade_id="TK-PEAK", area="Tokyo", load_profile="Peak"),
        make_trade(trade_id="KS-BASE", area="Kansai", load_profile="Base"),
    )

    contributions = contributing_trades(
        trade_book=positions_book,
        area="Tokyo",
        period=OCTOBER,
        profiles=BASE_PEAK,
    )

    assert [c.trade.trade_id for c in contributions] == ["TK-BASE", "TK-PEAK"]


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
        period=OCTOBER,
        profiles=BASE_ONLY,
    )

    assert [(c.trade.trade_id, c.applicable_hours) for c in contributions] == [
        ("A", Decimal("336")),
        ("B", Decimal("408")),
    ]


def test_contributing_trade_energy_sums_to_the_reported_net_mwh():
    """The drill-down's MWh column adds up to the number on the matrix.

    This holds across profiles too: a Base buy and a Peak sell contribute
    7,440 and -2,112 MWh, and those sum to October's reported net MWh. A
    trader can therefore reconcile the aggregate by reading down the column.
    """
    trade_book = book(
        make_trade(trade_id="BASE", load_profile="Base", volume_mw="10"),
        make_trade(trade_id="PEAK", load_profile="Peak",
                   buy_sell=BuySell.SELL, volume_mw="8"),
    )

    contributions = contributing_trades(
        trade_book=trade_book,
        area="Tokyo",
        period=OCTOBER,
        profiles=BASE_PEAK,
    )

    positions = calculate_positions(
        trade_book=trade_book,
        periods=(OCTOBER,),
        profiles=BASE_PEAK,
        supported_areas=TOKYO,
        supported_trade_types=FUTURES,
    )

    assert [c.energy_mwh for c in contributions] == [
        Decimal("7440"),
        Decimal("-2112"),
    ]
    assert sum(
        (c.energy_mwh for c in contributions), start=Decimal("0")
    ) == october_mwh(positions)


def test_a_contributing_sell_reports_negative_energy():
    """The drill-down signs energy by direction, so a sell reduces the total."""
    [contribution] = contributing_trades(
        trade_book=book(
            make_trade(buy_sell=BuySell.SELL, volume_mw="5",
                       start="2026-10-01", end="2026-10-15")
        ),
        area="Tokyo",
        period=OCTOBER,
        profiles=BASE_ONLY,
    )

    assert contribution.energy_mwh == Decimal("-1680")


def test_contributing_trades_excludes_trades_with_no_applicable_hours():
    """A trade must both overlap the period and deliver hours inside it.

    This is the same two-part rule the curve applies, so the drill-down can
    never show a trade that did not move the number: the September trade does
    not overlap October at all, and the Peak trade overlaps a Saturday on
    which Peak does not deliver.
    """
    saturday = reporting("2026-10-10", "2026-10-10", "2026-10-11")

    assert (
        contributing_trades(
            trade_book=book(make_trade(start="2026-09-01", end="2026-10-01")),
            area="Tokyo",
            period=OCTOBER,
            profiles=BASE_ONLY,
        )
        == ()
    )
    assert (
        contributing_trades(
            trade_book=book(make_trade(load_profile="Peak")),
            area="Tokyo",
            period=saturday,
            profiles=ProfileRegistry(profiles={"Peak": PEAK}),
        )
        == ()
    )
