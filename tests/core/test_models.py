"""Business semantics of the domain models.

Dataclass mechanics (frozen, slots, equality) are Python's behaviour and are
not tested here. What is tested is the four rules the position depends on:
direction carries the sign, a delivery interval must be positive, adjacent
half-open intervals do not overlap, and intersection clips to the overlap.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.models import BuySell, DeliveryPeriod, ExcludedTrade
from tests.builders import delivery, make_trade

pytestmark = pytest.mark.unit


def test_buy_contributes_positively_to_the_desk_position():
    trade = make_trade(buy_sell=BuySell.BUY, volume_mw="10")

    assert trade.volume_mw_direction == Decimal("10")


def test_sell_contributes_negatively_to_the_desk_position():
    trade = make_trade(buy_sell=BuySell.SELL, volume_mw="10")

    assert trade.volume_mw_direction == Decimal("-10")


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-11-01", "2026-10-01"),  # end before start
        ("2026-10-01", "2026-10-01"),  # zero-length: delivers nothing
    ],
)
def test_delivery_period_requires_start_before_end(start, end):
    with pytest.raises(ValueError):
        DeliveryPeriod(
            start=date.fromisoformat(start),
            end=date.fromisoformat(end),
        )


def test_adjacent_delivery_periods_do_not_overlap():
    """[Oct 1, Nov 1) and [Nov 1, Dec 1) meet at a boundary they do not share.

    This is the whole reason the interval is half-open: Oct-26 and Nov-26 can
    be summed without double counting 1 November.
    """
    october = delivery("2026-10-01", "2026-11-01")
    november = delivery("2026-11-01", "2026-12-01")

    assert october.overlap(november) is False
    assert november.overlap(october) is False
    assert october.intersection(november) is None


def test_overlapping_delivery_periods_report_an_overlap():
    october = delivery("2026-10-01", "2026-11-01")
    mid_october = delivery("2026-10-15", "2026-11-15")

    assert october.overlap(mid_october) is True


def test_intersection_clips_a_trade_to_the_reporting_period():
    trade_delivery = delivery("2026-10-01", "2026-11-01")
    reporting_period = delivery("2026-10-05", "2026-10-12")

    assert trade_delivery.intersection(reporting_period) == delivery(
        "2026-10-05", "2026-10-12"
    )


# --- Quarantined trades: which positions they mark incomplete -----------------

OCTOBER = delivery("2026-10-01", "2026-11-01")
NOVEMBER = delivery("2026-11-01", "2026-12-01")


def test_a_quarantined_trade_affects_only_its_own_area_and_delivery():
    excluded = ExcludedTrade(trade_id="T001", area="Tokyo", delivery=OCTOBER)

    assert excluded.may_affect("Tokyo", OCTOBER) is True
    assert excluded.may_affect("Tokyo", NOVEMBER) is False
    assert excluded.may_affect("Kansai", OCTOBER) is False


def test_an_unreadable_area_or_delivery_could_be_anything():
    """Over-marking is the safe direction: a position wrongly shown as
    complete is worse than one wrongly shown as incomplete."""
    unknown_area = ExcludedTrade(trade_id="T001", area=None, delivery=OCTOBER)
    unknown_dates = ExcludedTrade(trade_id="T002", area="Tokyo", delivery=None)

    assert unknown_area.may_affect("Kansai", OCTOBER) is True
    assert unknown_area.may_affect("Kansai", NOVEMBER) is False
    assert unknown_dates.may_affect("Tokyo", NOVEMBER) is True
    assert unknown_dates.may_affect("Kansai", NOVEMBER) is False
