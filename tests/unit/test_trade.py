"""Trade invariants and per-trade signed MWh (AC-03, AC-05, AC-06, AC-16, AC-17)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core import (
    DateInterval,
    Direction,
    InvalidPriceError,
    InvalidVolumeError,
    MissingValueError,
    UnsupportedTradeTypeError,
    parse_trade_type,
    register_trade_type,
)
from tests.builders import make_trade

pytestmark = pytest.mark.unit


class TestSignedMw:
    def test_buy_contributes_positive_mw(self) -> None:
        assert make_trade(direction=Direction.BUY, volume_mw=20).signed_mw == Decimal(20)

    def test_sell_contributes_negative_mw(self) -> None:
        assert make_trade(direction=Direction.SELL, volume_mw=5).signed_mw == Decimal(-5)


class TestMwhIn:
    def test_base_trade_over_one_day_delivers_volume_times_24(self) -> None:
        """AC-05: a 10 MW Base trade covering one complete day contributes 240 MWh."""
        trade = make_trade(volume_mw=10, start=date(2026, 10, 1), end=date(2026, 10, 2))

        day = DateInterval(date(2026, 10, 1), date(2026, 10, 2))
        assert trade.mwh_in(day) == Decimal(240)

    def test_sell_delivers_negative_mwh(self) -> None:
        trade = make_trade(direction=Direction.SELL, volume_mw=8)

        day = DateInterval(date(2026, 10, 10), date(2026, 10, 11))
        assert trade.mwh_in(day) == Decimal(-192)

    def test_trade_outside_the_period_contributes_exactly_zero(self) -> None:
        """AC-06: a trade with no overlap contributes nothing, not a near-zero value."""
        trade = make_trade(start=date(2027, 4, 1), end=date(2028, 4, 1))

        october = DateInterval(date(2026, 10, 1), date(2026, 11, 1))
        assert trade.mwh_in(october) == Decimal(0)

    def test_only_the_overlapping_days_contribute(self) -> None:
        """AC-06: a Q4 trade reports only its October days in an October window."""
        q4 = make_trade(volume_mw=15, start=date(2026, 10, 1), end=date(2027, 1, 1))

        october = DateInterval(date(2026, 10, 1), date(2026, 11, 1))
        assert q4.mwh_in(october) == Decimal(15 * 31 * 24)

    def test_exclusive_end_excludes_the_end_date(self) -> None:
        """AC-04: [10 Oct, 12 Oct) contributes on 10 and 11 October but not on the 12th."""
        weekend = make_trade(volume_mw=8, start=date(2026, 10, 10), end=date(2026, 10, 12))

        def day(d: int) -> DateInterval:
            return DateInterval(date(2026, 10, d), date(2026, 10, d + 1))

        assert weekend.mwh_in(day(9)) == Decimal(0)
        assert weekend.mwh_in(day(10)) == Decimal(192)
        assert weekend.mwh_in(day(11)) == Decimal(192)
        assert weekend.mwh_in(day(12)) == Decimal(0)

    def test_daily_contributions_sum_to_the_period_contribution(self) -> None:
        """Signed MWh is additive over a partition, which is what lets the weekly and
        monthly views be built from the same arithmetic as the daily one."""
        trade = make_trade(volume_mw=12, start=date(2026, 10, 1), end=date(2027, 1, 1))
        week = DateInterval(date(2026, 10, 5), date(2026, 10, 12))

        daily_total = sum(
            (
                trade.mwh_in(DateInterval(date(2026, 10, d), date(2026, 10, d + 1)))
                for d in range(5, 12)
            ),
            Decimal(0),
        )
        assert daily_total == trade.mwh_in(week)

    def test_product_text_does_not_affect_the_position(self) -> None:
        """AC-16: product is descriptive metadata and is never parsed for delivery dates."""
        october = DateInterval(date(2026, 10, 1), date(2026, 11, 1))
        honest = make_trade(product="Oct-26 Base")
        mislabelled = make_trade(product="Cal-30 Peak nonsense")

        assert honest.mwh_in(october) == mislabelled.mwh_in(october)

    def test_price_does_not_affect_the_position(self) -> None:
        """AC-17: price is validated and retained but has no physical position effect."""
        october = DateInterval(date(2026, 10, 1), date(2026, 11, 1))
        cheap = make_trade(price_jpy_kwh="0.01")
        expensive = make_trade(price_jpy_kwh="999.99")

        assert cheap.mwh_in(october) == expensive.mwh_in(october)


class TestValidation:
    @pytest.mark.parametrize("volume", [0, -5])
    def test_rejects_non_positive_volume(self, volume: int) -> None:
        """S5.2: direction carries the sign, so a negative volume would be a second,
        conflicting way to express a short."""
        with pytest.raises(InvalidVolumeError) as exc:
            make_trade(volume_mw=volume)

        assert "buy_sell=Sell" in str(exc.value), "the message must say what to do instead"

    @pytest.mark.parametrize("price", ["0", "-1.5"])
    def test_rejects_non_positive_price(self, price: str) -> None:
        with pytest.raises(InvalidPriceError):
            make_trade(price_jpy_kwh=price)

    @pytest.mark.parametrize(
        "field", ["trade_id", "counterparty", "area", "trade_type", "product"]
    )
    def test_rejects_empty_required_text(self, field: str) -> None:
        with pytest.raises(MissingValueError) as exc:
            make_trade(**{field: "   "})

        assert field in str(exc.value), "the message must identify the offending field (AC-14)"

    def test_trade_is_immutable(self) -> None:
        """Immutability is what lets a book be shared across the three views and across
        concurrent refreshes without defensive copying."""
        trade = make_trade()

        with pytest.raises(AttributeError):
            trade.volume_mw = Decimal(99)


class TestTradeType:
    def test_futures_is_recognised(self) -> None:
        assert parse_trade_type("Futures") == "Futures"

    @pytest.mark.parametrize("raw", ["futures", "FUTURES", " Futures "])
    def test_parse_accepts_case_and_whitespace_variants(self, raw: str) -> None:
        assert parse_trade_type(raw) == "Futures"

    def test_unknown_trade_type_is_rejected(self) -> None:
        with pytest.raises(UnsupportedTradeTypeError) as exc:
            parse_trade_type("Swap")

        assert "'Swap'" in str(exc.value)
        assert "Futures" in str(exc.value)

    def test_a_new_trade_type_is_registered_as_data(
        self, clean_trade_type_registry: None
    ) -> None:
        """An OTC forward becomes acceptable by registering a name. No position semantics
        are attached, because the brief defines none (S3.2)."""
        register_trade_type("OTC Forward")

        otc = make_trade(trade_type=parse_trade_type("otc forward"))
        october = DateInterval(date(2026, 10, 1), date(2026, 11, 1))

        assert otc.trade_type == "OTC Forward"
        assert otc.mwh_in(october) == make_trade().mwh_in(october)
