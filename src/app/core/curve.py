"""
Hourly net position curve.

The curve is the desk's net MW in every delivery hour of the reporting
horizon, one curve per area. Every reported number is read off it:

    net MWh   = sum of the curve over the hours in a period
    net MW    = that sum / the number of hours
    min / max = the shortest and longest single hour

Building the curve once and summarising it per period means:

* Base, Peak and any future profile net into the hours they actually share,
  instead of being reported as unrelated numbers.
* A period's average can never hide an hour where the desk is the other way
  round: the min and max come from the same curve.
* Any horizon or bucket shape is a cheap read, because the trades have
  already been placed once.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import accumulate

from app.core.errors import (
    PositionCalculationError,
    UnsupportedAreaError,
    UnsupportedTradeTypeError,
)
from app.core.models import (
    NO_EXPOSURE,
    ZERO,
    DeliveryPeriod,
    Exposure,
    Trade,
    TradeBook,
)
from app.core.profiles import HOURS_PER_DAY, LoadProfile, ProfileRegistry


@dataclass(frozen=True, slots=True)
class NetCurve:
    """Hourly net MW for one area across the reporting horizon.

    ``hourly_mw[i]`` is the net MW in hour ``i % 24`` of day ``i // 24``,
    counted from ``horizon.start``.
    """

    area: str
    horizon: DeliveryPeriod
    hourly_mw: tuple[Decimal, ...]

    def exposure(
        self,
        period: DeliveryPeriod,
        profile: LoadProfile,
    ) -> Exposure:
        """Summarise the curve over the hours ``profile`` delivers in ``period``."""

        values = self.values(period, profile)

        if not values:
            return NO_EXPOSURE

        return Exposure(
            hours=len(values),
            net_mwh=sum(values, ZERO),
            min_mw=min(values),
            max_mw=max(values),
        )

    def values(
        self,
        period: DeliveryPeriod,
        profile: LoadProfile,
    ) -> list[Decimal]:
        """The curve's net MW in each hour ``profile`` delivers in ``period``."""

        if not self.horizon.contains(period):
            raise PositionCalculationError(
                f"Period {period.start} to {period.end} is outside the "
                f"curve horizon {self.horizon.start} to {self.horizon.end}"
            )

        values: list[Decimal] = []

        for day in period.each_day():
            first_hour = _day_index(self.horizon, day) * HOURS_PER_DAY

            values.extend(
                self.hourly_mw[first_hour + hour]
                for hour in sorted(profile.hours_on(day))
            )

        return values


def build_curves(
    trade_book: TradeBook,
    horizon: DeliveryPeriod,
    profiles: ProfileRegistry,
    supported_areas: frozenset[str],
    supported_trade_types: frozenset[str],
) -> dict[str, NetCurve]:
    """Build one hourly net MW curve per supported area over ``horizon``.

    Two passes keep the cost linear in trades plus hours, rather than trades
    times hours, however long-dated the trades are:

    1. Each trade adds its signed MW to a daily step list on the day its
       delivery starts and removes it on the day it ends. A running sum of
       that list then gives every day's net MW for one area and profile.
    2. Each day's net MW is spread onto the hours its profile delivers that
       day, and the profiles of one area are added together.

    Every trade's area, trade type and profile is validated, even if it
    delivers outside the horizon, so a bad reference fails the run rather
    than vanishing.
    """

    daily_steps: dict[tuple[str, str], list[Decimal]] = {}

    for trade in trade_book:
        _validate_references(
            trade=trade,
            profiles=profiles,
            supported_areas=supported_areas,
            supported_trade_types=supported_trade_types,
        )

        overlap = trade.delivery.intersection(horizon)

        if overlap is None:
            continue

        steps = daily_steps.setdefault(
            (trade.area, trade.load_profile),
            [ZERO] * (horizon.days + 1),
        )

        steps[_day_index(horizon, overlap.start)] += trade.volume_mw_direction
        steps[_day_index(horizon, overlap.end)] -= trade.volume_mw_direction

    hourly: dict[str, list[Decimal]] = {
        area: [ZERO] * (horizon.days * HOURS_PER_DAY)
        for area in sorted(supported_areas)
    }

    for (area, profile_name), steps in daily_steps.items():
        _spread_onto_hours(
            hourly_mw=hourly[area],
            daily_mw=accumulate(steps[: horizon.days]),
            horizon=horizon,
            profile=profiles.get(profile_name),
        )

    return {
        area: NetCurve(
            area=area,
            horizon=horizon,
            hourly_mw=tuple(values),
        )
        for area, values in hourly.items()
    }


def _validate_references(
    trade: Trade,
    profiles: ProfileRegistry,
    supported_areas: frozenset[str],
    supported_trade_types: frozenset[str],
) -> None:
    """Fail on any trade that references unconfigured reference data.

    Area, trade type and load profile are all checked the same way: a
    mistyped value is never guessed at or silently dropped, because a book
    missing a trade still looks complete and can imply the wrong hedge.
    """

    if trade.area not in supported_areas:
        raise UnsupportedAreaError(
            f"Unsupported area: {trade.area} "
            f"(trade {trade.trade_id})"
        )

    if trade.trade_type not in supported_trade_types:
        raise UnsupportedTradeTypeError(
            f"Unsupported trade type: {trade.trade_type} "
            f"(trade {trade.trade_id})"
        )

    profiles.get(trade.load_profile)


def _spread_onto_hours(
    hourly_mw: list[Decimal],
    daily_mw: Iterable[Decimal],
    horizon: DeliveryPeriod,
    profile: LoadProfile,
) -> None:
    """Add each day's net MW to the hours the profile delivers that day."""

    for day, net_mw in zip(horizon.each_day(), daily_mw, strict=True):
        if net_mw == ZERO:
            continue

        first_hour = _day_index(horizon, day) * HOURS_PER_DAY

        for hour in profile.hours_on(day):
            hourly_mw[first_hour + hour] += net_mw


def _day_index(horizon: DeliveryPeriod, day: date) -> int:
    """Days from the start of the horizon to ``day``."""
    return (day - horizon.start).days
