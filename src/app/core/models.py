"""
Core models for power position calculation.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal 
from enum import StrEnum

class BuySell(StrEnum):
    """Direction of a trade from desk's perspective."""
    BUY = "Buy"
    SELL = "Sell"

    @property 
    def sign(self) -> int:
        """Return the position sign associated with the direction."""
        return 1 if self is BuySell.BUY else -1

@dataclass(frozen=True, slots=True)
class DeliveryPeriod:
    """
    Half open delivery interval.

    Eg. 
    T003 Oct-26 Base, start date: 2026-10-01, end date: 2026-11-01
    Delivery period: [2026-10-01, 2026-11-01), excludes 2026-11-01

    Adjacent products and reporting periods meet at the same boundary without overlaps/ special date handling
    """

    start:date
    end:date

    def __post_init__(self) -> None: 
        if self.start >= self.end:
            raise ValueError(
                "Delivery period start date must be before end date."
            )

    def overlap(self, other: DeliveryPeriod) -> bool:
        """Return when two delivery periods overlap."""
        return self.start < other.end and other.start < self.end

    def intersection(self, other: DeliveryPeriod) -> DeliveryPeriod | None:
        """Return overlapping interval if it exists."""
        start = max(self.start, other.start)
        end = min(self.end, other.end)

        if start >= end:
            return None

        return DeliveryPeriod(start=start, end=end)
    
@dataclass(frozen=True, slots=True)
class Trade: 
    """Normalized trade used by the position engine."""

    trade_id: str
    area: str
    trade_type: str
    buy_sell: BuySell
    load_profile: str
    delivery: DeliveryPeriod
    volume_mw: Decimal

    @property
    def volume_mw_direction(self) -> Decimal: 
        """Return MW volume with buy/sell direction applied."""
        return self.volume_mw * self.buy_sell.sign

@dataclass(frozen=True, slots=True)
class TradeBook:
    """Snapshot of normalized trades."""

    trades: tuple[Trade, ...]

    def __iter__(self) -> Iterator[Trade]:
        return iter(self.trades)

    def __len__(self) -> int: 
        return len(self.trades)


@dataclass(frozen=True, slots=True)
class ReportingPeriod: 
    """Period displayed in a position view."""

    label: str
    delivery: DeliveryPeriod

@dataclass(frozen=True, slots=True)
class Position: 
    """Net position for respective area and reporting period."""

    area: str
    load_profile:str
    period: ReportingPeriod
    net_position_mw: Decimal


