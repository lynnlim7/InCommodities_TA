"""Explicit constructors for test scenarios.

These exist only to remove repetitive noise. Every value a business scenario
depends on is still passed in by the test that depends on it, so each test
reads as a complete trade book on its own.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from app.core.models import (
    BuySell,
    DeliveryPeriod,
    Position,
    ReportingPeriod,
    Trade,
    TradeBook,
)


def delivery(start: str, end: str) -> DeliveryPeriod:
    """Half-open delivery interval from ISO date strings."""
    return DeliveryPeriod(
        start=date.fromisoformat(start),
        end=date.fromisoformat(end),
    )


def reporting(label: str, start: str, end: str) -> ReportingPeriod:
    return ReportingPeriod(label=label, delivery=delivery(start, end))


def make_trade(
    *,
    trade_id: str = "T001",
    area: str = "Tokyo",
    trade_type: str = "Futures",
    buy_sell: BuySell = BuySell.BUY,
    load_profile: str = "Base",
    start: str = "2026-10-01",
    end: str = "2026-11-01",
    volume_mw: str = "10",
    product: str = "Oct-26 Base",
) -> Trade:
    return Trade(
        trade_id=trade_id,
        area=area,
        trade_type=trade_type,
        buy_sell=buy_sell,
        load_profile=load_profile,
        delivery=delivery(start, end),
        volume_mw=Decimal(volume_mw),
        product=product,
    )


def book(*trades: Trade) -> TradeBook:
    return TradeBook(trades=trades)


def position_for(
    positions: Iterable[Position],
    *,
    area: str,
    load_profile: str,
    period: ReportingPeriod,
) -> Position:
    """Return the single position row for one aggregation key.

    The engine emits a row for every area x profile x period combination, so a
    test asserting on one business scenario has to select its row. Unpacking a
    one-element list also asserts the engine never emits a duplicate key.
    """
    [found] = [
        position
        for position in positions
        if position.area == area
        and position.load_profile == load_profile
        and position.period == period
    ]
    return found
