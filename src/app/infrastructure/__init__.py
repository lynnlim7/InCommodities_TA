"""Adapters for the outside world: reading trades, and reporting what could not be read.

Depends on ``app.core``; nothing in ``app.core`` depends on this package.
"""

from __future__ import annotations

from app.infrastructure.csv_repository import DEFAULT_TRADES_CSV, CsvTradeRepository
from app.infrastructure.errors import (
    InputError,
    RowError,
    TradeBookValidationError,
    TradeSourceError,
    ValidationReport,
)
from app.infrastructure.raw import CSV_HEADERS, RawTradeRow
from app.infrastructure.repository import TradeRepository

__all__ = [
    "CSV_HEADERS",
    "DEFAULT_TRADES_CSV",
    "CsvTradeRepository",
    "InputError",
    "RawTradeRow",
    "RowError",
    "TradeBookValidationError",
    "TradeRepository",
    "TradeSourceError",
    "ValidationReport",
]
