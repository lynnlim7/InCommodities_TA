"""Pure position core: no filesystem, no clock, no framework, no presentation.

Everything in this package is deterministic and independently testable
(requirements.md S13.2, S13.3). Nothing here imports from ``infrastructure``,
``interfaces``, or ``services``; the dependency arrow only ever points inward.
"""

from __future__ import annotations

from app.core.direction import Direction
from app.core.engine import average_mw, calculate_views, net_mwh
from app.core.errors import (
    DomainError,
    DuplicateTradeIdError,
    InvalidIntervalError,
    InvalidPriceError,
    InvalidVolumeError,
    MissingValueError,
    UnsupportedDirectionError,
    UnsupportedLoadProfileError,
    UnsupportedTradeTypeError,
)
from app.core.interval import HOURS_PER_DAY, DateInterval
from app.core.periods import (
    Granularity,
    ReportPeriod,
    daily_periods,
    monthly_periods,
    reporting_periods,
    reporting_window,
    weekly_periods,
)
from app.core.position import Position, classify
from app.core.profiles import (
    BASE,
    BaseProfile,
    LoadProfile,
    parse_profile,
    register_profile,
    registered_profiles,
)
from app.core.results import PositionRow, PositionView, PositionViews
from app.core.trade import (
    KNOWN_TRADE_TYPES,
    Trade,
    TradeBook,
    parse_trade_type,
    register_trade_type,
)

__all__ = [
    "BASE",
    "HOURS_PER_DAY",
    "KNOWN_TRADE_TYPES",
    "BaseProfile",
    "DateInterval",
    "Direction",
    "DomainError",
    "DuplicateTradeIdError",
    "Granularity",
    "InvalidIntervalError",
    "InvalidPriceError",
    "InvalidVolumeError",
    "LoadProfile",
    "MissingValueError",
    "Position",
    "PositionRow",
    "PositionView",
    "PositionViews",
    "ReportPeriod",
    "Trade",
    "TradeBook",
    "UnsupportedDirectionError",
    "UnsupportedLoadProfileError",
    "UnsupportedTradeTypeError",
    "average_mw",
    "calculate_views",
    "classify",
    "daily_periods",
    "monthly_periods",
    "net_mwh",
    "parse_profile",
    "parse_trade_type",
    "register_profile",
    "register_trade_type",
    "registered_profiles",
    "reporting_periods",
    "reporting_window",
    "weekly_periods",
]
