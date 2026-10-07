"""
Core models for power position calculation.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal("0")


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

    Adjacent products and reporting periods meet at the same boundary
    without overlaps or special date handling.
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

    def contains(self, other: DeliveryPeriod) -> bool:
        """Return whether ``other`` lies wholly inside this period."""
        return self.start <= other.start and other.end <= self.end

    @property
    def days(self) -> int:
        """Number of delivery days in the period."""
        return (self.end - self.start).days

    def each_day(self) -> Iterator[date]:
        """Every delivery day in the period, in order."""
        for offset in range(self.days):
            yield self.start + timedelta(days=offset)

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
    product: str = ""

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
class Exposure:
    """Net MWh, average net MW and the min/max hour over a set of delivery hours."""

    hours: int
    net_mwh: Decimal
    min_mw: Decimal
    max_mw: Decimal

    @property
    def net_mw(self) -> Decimal:
        """Average net MW over the hours, or zero when there are none."""
        if self.hours == 0:
            return ZERO

        return self.net_mwh / self.hours


NO_EXPOSURE = Exposure(hours=0, net_mwh=ZERO, min_mw=ZERO, max_mw=ZERO)


@dataclass(frozen=True, slots=True)
class BlockPosition:
    """Exposure over the hours one reporting block covers, e.g. Peak."""

    name: str
    exposure: Exposure


@dataclass(frozen=True, slots=True)
class Position:
    """Net position for respective area and reporting period."""

    area: str
    period: ReportingPeriod
    exposure: Exposure
    blocks: tuple[BlockPosition, ...] = ()

    @property
    def net_position_mw(self) -> Decimal:
        """Average net MW over every hour of the period."""
        return self.exposure.net_mw

    @property
    def net_position_mwh(self) -> Decimal:
        """Net MWh delivered into the period."""
        return self.exposure.net_mwh

    def block(self, name: str) -> Exposure:
        """Return the exposure for one reporting block by name."""
        for block in self.blocks:
            if block.name == name:
                return block.exposure

        raise KeyError(name)


@dataclass(frozen=True, slots=True)
class TradeContribution:
    """One trade's applicable delivery inside a reporting period."""

    trade: Trade
    applicable_hours: Decimal

    @property
    def energy_mwh(self) -> Decimal:
        """Signed energy this trade delivers into the period."""
        return self.trade.volume_mw_direction * self.applicable_hours




@dataclass(frozen=True, slots=True)
class ReferenceData:
    """Configured areas, trade types and load profiles a book is checked against."""

    areas: frozenset[str]
    trade_types: frozenset[str]
    load_profiles: frozenset[str]


@dataclass(frozen=True, slots=True)
class ExcludedTrade:
    """A quarantined trade, with whatever could still be read of it."""

    trade_id: str | None
    area: str | None
    delivery: DeliveryPeriod | None

    def may_affect(self, area: str, period: DeliveryPeriod) -> bool:
        area_matches = self.area is None or self.area == area
        period_matches = self.delivery is None or self.delivery.overlap(period)
        return area_matches and period_matches
