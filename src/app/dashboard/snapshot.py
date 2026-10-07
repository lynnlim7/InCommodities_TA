"""
Build immutable data snapshot consumed by the dashboard. 

Snapshot represents one consistent application state: 

    configuration + trades -> reporting periods -> positions

All positions are calculated once when the snapshot is created.
Rendering performs lookups and never recalculates position data. 
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.adapters.csv_repository import (
    DEFAULT_TRADES_CSV,
    CsvTradeRepository,
    LoadResult,
)
from app.config.loader import (
    AREAS_YAML,
    LOAD_PROFILES_YAML,
    TRADE_TYPES_YAML,
    load_yaml,
)
from app.config.profile_registry import build_profile_registry
from app.config.schema import AreasConfig, LoadProfilesConfig, TradeTypesConfig
from app.core.calculations import calculate_positions, contributing_trades
from app.core.models import (
    DeliveryPeriod,
    ExcludedTrade,
    Position,
    ReferenceData,
    ReportingPeriod,
    TradeBook,
    TradeContribution,
)
from app.core.periods import daily_periods, monthly_periods, weekly_periods
from app.core.profiles import ProfileRegistry
from app.dashboard.formatting import (
    format_daily_label,
    format_monthly_label,
    format_weekly_label,
)

JST = ZoneInfo("Asia/Tokyo")
AS_OF = date(2026, 10, 1)

LabelFormatter = Callable[[DeliveryPeriod], str]
PositionKey = tuple[str, ReportingPeriod]


@dataclass(frozen=True, slots=True)
class PositionView:
    """Reporting periods and presentation metadata for one horizon."""

    title: str
    periods: tuple[ReportingPeriod, ...]
    format_label: LabelFormatter


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Immutable application state produced from one trade book load."""

    as_of: date
    refreshed_at: datetime
    trade_book: TradeBook
    load_result: LoadResult
    profiles: ProfileRegistry
    areas: tuple[str, ...]
    trade_types: tuple[str, ...]
    views: tuple[PositionView, ...]
    positions: tuple[Position, ...]
    position_index: dict[PositionKey, Position]

    def position(
        self,
        *,
        area: str,
        period: ReportingPeriod,
    ) -> Position:
        """Return the calculated position for one reporting cell."""
        return self.position_index[(area, period)]

    def excluded_trades(
        self,
        *,
        area: str,
        period: ReportingPeriod,
    ) -> tuple[ExcludedTrade, ...]:
        """Quarantined trades that could have moved this position."""
        return tuple(
            trade
            for trade in self.load_result.excluded_trades
            if trade.may_affect(area, period.delivery)
        )

    def contributions(
        self,
        *,
        area: str,
        period: ReportingPeriod,
    ) -> tuple[TradeContribution, ...]:
        """Return trades for reported position."""
        return contributing_trades(
            trade_book=self.trade_book,
            area=area,
            period=period,
            profiles=self.profiles,
        )


def load_snapshot(
    as_of: date = AS_OF,
    trades_csv: Path = DEFAULT_TRADES_CSV,
) -> Snapshot:
    """Load application inputs and calculate one consistent position snapshot."""
    areas_config = load_yaml(AREAS_YAML, AreasConfig)
    trade_types_config = load_yaml(TRADE_TYPES_YAML, TradeTypesConfig)
    profiles_config = load_yaml(LOAD_PROFILES_YAML, LoadProfilesConfig)
    profiles = build_profile_registry(profiles_config)

    reference = ReferenceData(
        areas=frozenset(areas_config.areas),
        trade_types=frozenset(trade_types_config.trade_types),
        load_profiles=frozenset(name for name, _ in profiles.items()),
    )

    load_result = CsvTradeRepository(path=trades_csv, reference=reference).load()
    trade_book = load_result.trade_book

    views = _build_views(as_of)
    periods = _reporting_periods(views)
    areas = tuple(sorted(areas_config.areas))

    positions = calculate_positions(
        trade_book=trade_book,
        periods=periods,
        profiles=profiles,
        supported_areas=reference.areas,
        supported_trade_types=reference.trade_types,
    )

    return Snapshot(
        as_of=as_of,
        refreshed_at=datetime.now(UTC).astimezone(JST),
        trade_book=trade_book,
        load_result=load_result,
        profiles=profiles,
        areas=areas,
        trade_types=tuple(trade_types_config.trade_types),
        views=views,
        positions=positions,
        position_index=_index_positions(positions),
    )


def _build_views(as_of: date) -> tuple[PositionView, ...]:
    """Build the reporting horizons shown by the dashboard."""
    return (
        PositionView(
            title="Next 7 days",
            periods=daily_periods(as_of=as_of, count=7),
            format_label=format_daily_label,
        ),
        PositionView(
            title="Next 4 weeks",
            periods=weekly_periods(as_of=as_of, count=4),
            format_label=format_weekly_label,
        ),
        PositionView(
            title="Next 12 months",
            periods=monthly_periods(as_of=as_of, count=12),
            format_label=format_monthly_label,
        ),
    )


def _reporting_periods(
    views: tuple[PositionView, ...],
) -> tuple[ReportingPeriod, ...]:
    """Flatten all reporting horizons into calculation periods."""
    return tuple(
        period
        for view in views
        for period in view.periods
    )


def _index_positions(
    positions: tuple[Position, ...],
) -> dict[PositionKey, Position]:
    """Index calculated positions for constant-time dashboard lookup."""
    return {
        (
            position.area,
            position.period,
        ): position
        for position in positions
    }