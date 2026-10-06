"""
Calculate net power positions.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.core.errors import UnsupportedAreaError
from app.core.models import (
    Position,
    ReportingPeriod,
    TradeBook,
)
from app.core.profiles import ProfileRegistry


ZERO = Decimal("0")


def calculate_positions(
    trade_book: TradeBook,
    periods: tuple[ReportingPeriod, ...],
    profiles: ProfileRegistry,
    supported_areas: frozenset[str],
) -> tuple[Position, ...]:
    """
    Calculate time-weighted net MW positions.

    Positions are aggregated by area, load profile, and reporting period.
    """

    weighted_totals: dict[
        tuple[str, str, ReportingPeriod],
        Decimal,
    ] = defaultdict(lambda: ZERO)

    for trade in trade_book:
        if trade.area not in supported_areas:
            raise UnsupportedAreaError(
                f"Unsupported area: {trade.area} "
                f"(trade {trade.trade_id})"
            )

        profile = profiles.get(
            trade.load_profile
        )

        for period in periods:
            overlap = trade.delivery.intersection(
                period.delivery
            )

            if overlap is None:
                continue

            delivery_hours = profile.delivery_hours(
                overlap
            )

            if delivery_hours == ZERO:
                continue

            key = (
                trade.area,
                trade.load_profile,
                period,
            )

            weighted_totals[key] += (
                trade.volume_mw_direction
                * delivery_hours
            )

    return _build_positions(
        weighted_totals=weighted_totals,
        periods=periods,
        profiles=profiles,
        supported_areas=supported_areas,
    )

def _build_positions(
    weighted_totals: dict[
        tuple[str, str, ReportingPeriod],
        Decimal,
    ],
    periods: tuple[ReportingPeriod, ...],
    profiles: ProfileRegistry,
    supported_areas: frozenset[str],
) -> tuple[Position, ...]:
    """Build deterministic position rows including zero positions."""

    positions: list[Position] = []

    for area in sorted(supported_areas):
        for profile_name, profile in profiles.items():
            for period in periods:

                period_hours = profile.delivery_hours(
                    period.delivery
                )

                weighted_total = weighted_totals.get(
                    (
                        area,
                        profile_name,
                        period,
                    ),
                    ZERO,
                )

                net_position_mw = (
                    weighted_total / period_hours
                    if period_hours > ZERO
                    else ZERO
                )

                positions.append(
                    Position(
                        area=area,
                        load_profile=profile_name,
                        period=period,
                        net_position_mw=net_position_mw,
                    )
                )

    return tuple(positions)