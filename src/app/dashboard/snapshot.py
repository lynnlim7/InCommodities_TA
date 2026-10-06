"""Application composition: one load, one calculation, one refresh timestamp.

This is the only place the dashboard assembles the pipeline:

    configuration + trades.csv -> TradeBook -> reporting periods ->
    calculate_positions() -> Position[]

It computes all three horizons once per data load and captures the refresh
time at that boundary, so every table on the page describes the same snapshot.
No Streamlit import: the composition stays testable and the caching decision
belongs to the renderer.
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

# Fixed reporting date for this MVP. The business as-of date is an input, not
# something read from the machine clock, so a run is reproducible.
AS_OF = date(2026, 10, 1)

LabelFormatter = Callable[[DeliveryPeriod], str]


@dataclass(frozen=True, slots=True)
class PositionView:
    """One reporting horizon of an area/profile position table."""

    title: str
    periods: tuple[ReportingPeriod, ...]
    format_label: LabelFormatter


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Everything the page renders, from one load of one trade book."""

    as_of: date
    refreshed_at: datetime
    trade_book: TradeBook
    profiles: ProfileRegistry
    areas: tuple[str, ...]
    trade_types: tuple[str, ...]
    views: tuple[PositionView, ...]
    positions: tuple[Position, ...]
    # Built once at load time so rendering a row is a lookup, never a
    # recalculation.
    position_index: dict[tuple[str, str, ReportingPeriod], Decimal]

    def profile_names(self) -> tuple[str, ...]:
        """Configured load profiles, in configuration order."""
        return tuple(self.profiles.profiles)

    def net_position_mw(
        self,
        *,
        area: str,
        load_profile: str,
        period: ReportingPeriod,
    ) -> Decimal:
        """Look up one already-calculated position. Never recalculates."""
        return self.position_index[(area, load_profile, period)]

    def contributions(
        self,
        *,
        area: str,
        load_profile: str,
        period: ReportingPeriod,
    ) -> tuple[TradeContribution, ...]:
        """Trades that produced one position, per the engine's own rule."""
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
    """Load configuration and trades, then calculate every reported view once."""

    areas_config = load_yaml(AREAS_YAML, AreasConfig)
    trade_types_config = load_yaml(TRADE_TYPES_YAML, TradeTypesConfig)
    profiles = build_profile_registry(load_yaml(LOAD_PROFILES_YAML, LoadProfilesConfig))

    trade_book = CsvTradeRepository(path=trades_csv).load()

    # The refresh time belongs to the data load, not to rendering: it is
    # stamped once here so every table on the page reports the same snapshot.
    refreshed_at = datetime.now(UTC).astimezone(JST)

    views = (
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

    areas = frozenset(areas_config.areas)

    positions = calculate_positions(
        trade_book=trade_book,
        periods=tuple(period for view in views for period in view.periods),
        profiles=profiles,
        supported_areas=areas,
    )

    return Snapshot(
        as_of=as_of,
        refreshed_at=refreshed_at,
        trade_book=trade_book,
        profiles=profiles,
        areas=tuple(sorted(areas)),
        trade_types=tuple(trade_types_config.trade_types),
        views=views,
        positions=positions,
        position_index={
            (
                position.area,
                position.load_profile,
                position.period,
            ): position.net_position_mw
            for position in positions
        },
    )
