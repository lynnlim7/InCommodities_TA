"""
Calculate net power positions.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.curve import NetCurve, build_curves
from app.core.models import (
    ZERO,
    BlockPosition,
    DeliveryPeriod,
    Position,
    ReportingPeriod,
    Trade,
    TradeBook,
    TradeContribution,
)
from app.core.profiles import ContinuousProfile, LoadProfile, ProfileRegistry

EVERY_HOUR = ContinuousProfile()


def calculate_positions(
    trade_book: TradeBook,
    periods: tuple[ReportingPeriod, ...],
    profiles: ProfileRegistry,
    supported_areas: frozenset[str],
    supported_trade_types: frozenset[str],
    blocks: tuple[str, ...] = (),
) -> tuple[Position, ...]:
    """Calculate net MWh and net MW positions, read off each area's hourly curve."""

    if not periods:
        return ()

    curves = build_curves(
        trade_book=trade_book,
        horizon=_horizon(periods),
        profiles=profiles,
        supported_areas=supported_areas,
        supported_trade_types=supported_trade_types,
    )

    block_profiles = tuple(
        (name, profiles.get(name))
        for name in blocks
    )

    return tuple(
        _position(curve, period, block_profiles)
        for curve in curves.values()
        for period in periods
    )


def _position(
    curve: NetCurve,
    period: ReportingPeriod,
    block_profiles: tuple[tuple[str, LoadProfile], ...],
) -> Position:
    """Read one area's position for one period off its curve."""

    return Position(
        area=curve.area,
        period=period,
        exposure=curve.exposure(period.delivery, EVERY_HOUR),
        blocks=tuple(
            BlockPosition(
                name=name,
                exposure=curve.exposure(period.delivery, profile),
            )
            for name, profile in block_profiles
        ),
    )


def _horizon(
    periods: tuple[ReportingPeriod, ...],
) -> DeliveryPeriod:
    """The smallest interval covering every reporting period."""

    return DeliveryPeriod(
        start=min(period.delivery.start for period in periods),
        end=max(period.delivery.end for period in periods),
    )


def _applicable_hours(
    trade: Trade,
    period: ReportingPeriod,
    profile: LoadProfile,
) -> Decimal | None:
    """Hours this trade delivers inside the period, or None if it contributes nothing."""

    overlap = trade.delivery.intersection(
        period.delivery
    )

    if overlap is None:
        return None

    delivery_hours = profile.delivery_hours(
        overlap
    )

    if delivery_hours == ZERO:
        return None

    return delivery_hours


def contributing_trades(
    trade_book: TradeBook,
    area: str,
    period: ReportingPeriod,
    profiles: ProfileRegistry,
) -> tuple[TradeContribution, ...]:
    """Return the trades that produced one aggregated position, in book order."""

    return tuple(
        TradeContribution(
            trade=trade,
            applicable_hours=delivery_hours,
        )
        for trade in trade_book
        if trade.area == area
        and (
            delivery_hours := _applicable_hours(
                trade,
                period,
                profiles.get(trade.load_profile),
            )
        )
        is not None
    )
