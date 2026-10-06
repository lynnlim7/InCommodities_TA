"""The hourly net position curve.

Every reported number is read off this curve, so these tests check it hour by
hour: that each profile lands on exactly the hours it delivers, that trades
starting and ending inside the horizon step on and off on the right day, and
that a period outside the horizon is refused rather than read wrongly.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.curve import build_curves
from app.core.errors import PositionCalculationError
from app.core.models import BuySell
from app.core.profiles import (
    ContinuousProfile,
    HourlyWindowProfile,
    ProfileRegistry,
)
from tests.helpers import book, delivery, make_trade

pytestmark = pytest.mark.unit

PEAK = HourlyWindowProfile(start_hour=8, end_hour=20, weekdays=frozenset({0, 1, 2, 3, 4}))
PROFILES = ProfileRegistry(
    profiles={
        "Base": ContinuousProfile(),
        "Peak": PEAK,
    }
)
TOKYO = frozenset({"Tokyo"})
FUTURES = frozenset({"Futures"})

# Monday 5 Oct to Sunday 11 Oct 2026: 168 hours.
WEEK = delivery("2026-10-05", "2026-10-12")


def tokyo_curve(*trades, horizon=WEEK):
    return build_curves(
        trade_book=book(*trades),
        horizon=horizon,
        profiles=PROFILES,
        supported_areas=TOKYO,
        supported_trade_types=FUTURES,
    )["Tokyo"]


def hour(curve, day, hour_of_day):
    """Net MW in one hour, addressed by calendar date and hour of day."""
    index = (date.fromisoformat(day) - curve.horizon.start).days * 24 + hour_of_day
    return curve.hourly_mw[index]


def test_a_base_trade_is_on_every_hour_of_the_horizon():
    curve = tokyo_curve(make_trade(load_profile="Base", volume_mw="10"))

    assert len(curve.hourly_mw) == 168
    assert set(curve.hourly_mw) == {Decimal("10")}


def test_a_peak_trade_is_only_on_weekday_daytime_hours():
    """08:00-20:00 Monday to Friday, and nothing at night or at the weekend."""
    curve = tokyo_curve(make_trade(load_profile="Peak", volume_mw="10"))

    assert hour(curve, "2026-10-05", 8) == Decimal("10")  # Monday 08:00
    assert hour(curve, "2026-10-05", 19) == Decimal("10")  # Monday 19:00
    assert hour(curve, "2026-10-05", 20) == Decimal("0")  # Monday 20:00
    assert hour(curve, "2026-10-05", 7) == Decimal("0")  # Monday 07:00
    assert hour(curve, "2026-10-10", 12) == Decimal("0")  # Saturday noon
    assert sum(curve.hourly_mw) == Decimal("10") * Decimal("60")


def test_a_trade_steps_on_and_off_at_its_delivery_boundaries():
    """A weekend trade [10 Oct, 12 Oct) is on Saturday and Sunday only.

    The half-open end means it is off again at midnight going into Monday,
    which here is also the end of the horizon.
    """
    curve = tokyo_curve(
        make_trade(buy_sell=BuySell.SELL, volume_mw="8",
                   start="2026-10-10", end="2026-10-12"),
    )

    assert hour(curve, "2026-10-09", 23) == Decimal("0")  # Friday 23:00
    assert hour(curve, "2026-10-10", 0) == Decimal("-8")  # Saturday 00:00
    assert hour(curve, "2026-10-11", 23) == Decimal("-8")  # Sunday 23:00


def test_a_long_dated_trade_is_clipped_to_the_horizon():
    """A full calendar-year trade only adds its hours inside the horizon."""
    curve = tokyo_curve(
        make_trade(volume_mw="20", start="2026-01-01", end="2027-01-01"),
    )

    assert sum(curve.hourly_mw) == Decimal("20") * Decimal("168")


def test_an_area_with_no_trades_still_has_a_flat_curve():
    """Every supported area gets a curve, so a flat area is reported, not missing."""
    curves = build_curves(
        trade_book=book(make_trade(area="Tokyo")),
        horizon=WEEK,
        profiles=PROFILES,
        supported_areas=frozenset({"Tokyo", "Kansai"}),
        supported_trade_types=FUTURES,
    )

    assert set(curves["Kansai"].hourly_mw) == {Decimal("0")}


def test_the_curve_summarises_only_the_hours_a_profile_delivers():
    """Base 10 MW plus Peak sell 8 MW: +2 in peak hours, +10 in the rest."""
    curve = tokyo_curve(
        make_trade(trade_id="B", load_profile="Base", volume_mw="10"),
        make_trade(trade_id="P", load_profile="Peak", buy_sell=BuySell.SELL, volume_mw="8"),
    )

    base = curve.exposure(WEEK, PROFILES.get("Base"))
    peak = curve.exposure(WEEK, PROFILES.get("Peak"))

    assert (peak.hours, peak.net_mw) == (60, Decimal("2"))
    assert base.hours == 168
    assert base.net_mw == (Decimal("10") * 168 - Decimal("8") * 60) / 168
    assert (base.min_mw, base.max_mw) == (Decimal("2"), Decimal("10"))


def test_reading_a_period_outside_the_horizon_fails():
    """Reading past the horizon would index the wrong hours, so it is refused."""
    curve = tokyo_curve(make_trade())

    with pytest.raises(PositionCalculationError):
        curve.exposure(delivery("2026-10-11", "2026-10-13"), ContinuousProfile())
