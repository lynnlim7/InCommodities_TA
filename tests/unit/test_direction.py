"""Direction and the Buy-positive / Sell-negative sign convention (AC-03)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core import Direction, UnsupportedDirectionError

pytestmark = pytest.mark.unit


def test_buy_is_positive_and_sell_is_negative() -> None:
    assert Direction.BUY.sign == Decimal(1)
    assert Direction.SELL.sign == Decimal(-1)


@pytest.mark.parametrize("raw", ["Buy", "buy", "BUY", "  Buy  "])
def test_parse_accepts_case_and_whitespace_variants(raw: str) -> None:
    assert Direction.parse(raw) is Direction.BUY


def test_parse_rejects_unknown_direction_and_names_the_supported_values() -> None:
    with pytest.raises(UnsupportedDirectionError) as exc:
        Direction.parse("Short")

    message = str(exc.value)
    assert "'Short'" in message, "the offending value must appear in the message (AC-14)"
    assert "Buy" in message and "Sell" in message


def test_parse_rejects_empty_direction() -> None:
    with pytest.raises(UnsupportedDirectionError):
        Direction.parse("")
