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
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config.loader import (
    AREAS_YAML,
    LOAD_PROFILES_YAML,
    TRADE_TYPES_YAML,
    load_yaml,
)
from app.config.profiles import build_profile_registry
from app.config.schema import AreasConfig, LoadProfilesConfig, TradeTypesConfig
from app.core.calculations import calculate_positions, contributing_trades
from app.core.models import (
    DeliveryPeriod,
    Position,
    ReportingPeriod,
    TradeBook,
    TradeContribution,
)
from app.core.periods import daily_periods, monthly_periods, weekly_periods
from app.core.profiles import ProfileRegistry
from app.dashboard.format import (
    format_daily_label,
    format_monthly_label,
    format_weekly_label,
)
from app.infrastructure.csv_repository import DEFAULT_TRADES_CSV, CsvTradeRepository

JST = ZoneInfo("Asia/Tokyo")
AS_OF = date(2026, 10, 1)

LabelFormatter = Callable[[DeliveryPeriod], str]
PositionKey = tuple[str, str, ReportingPeriod]


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
    profiles: ProfileRegistry
    areas: tuple[str, ...]
    trade_types: tuple[str, ...]
    views: tuple[PositionView, ...]
    positions: tuple[Position, ...]
    position_index: dict[PositionKey, Decimal]

    @property
    def profile_names(self) -> tuple[str, ...]:

        return tuple(self.profiles.profiles)

    def net_position_mw(
        self,
        *,
        area: str,
        load_profile: str,
        period: ReportingPeriod,
    ) -> Decimal:
        """Return calculated net position."""
        return self.position_index[(area, load_profile, period)]

    def contributions(
        self,
        *,
        area: str,
        load_profile: str,
        period: ReportingPeriod,
    ) -> tuple[TradeContribution, ...]:
        """Return trades for reported position."""
        return contributing_trades(
            trade_book=self.trade_book,
            area=area,
            load_profile=load_profile,
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
    profiles = _load_profiles()
    trade_book = CsvTradeRepository(path=trades_csv).load()

    views = _build_views(as_of)
    periods = _reporting_periods(views)
    areas = tuple(sorted(areas_config.areas))

    positions = calculate_positions(
        trade_book=trade_book,
        periods=periods,
        profiles=profiles,
        supported_areas=frozenset(areas),
    )

    return Snapshot(
        as_of=as_of,
        refreshed_at=datetime.now(UTC).astimezone(JST),
        trade_book=trade_book,
        profiles=profiles,
        areas=areas,
        trade_types=tuple(trade_types_config.trade_types),
        views=views,
        positions=positions,
        position_index=_index_positions(positions),
    )


def _load_profiles() -> ProfileRegistry:
    """Load and build the configured load-profile registry."""
    config = load_yaml(LOAD_PROFILES_YAML, LoadProfilesConfig)
    return build_profile_registry(config)


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
) -> dict[PositionKey, Decimal]:
    """Index calculated positions for constant-time dashboard lookup."""
    return {
        (
            position.area,
            position.load_profile,
            position.period,
        ): position.net_position_mw
        for position in positions
    }