"""
Errors raised while loading trade data. 
"""

from __future__ import annotations

from dataclasses import dataclass


class TradeSourceError(Exception):
    """Trade source cannot be read or has an invalid structure."""

@dataclass(frozen=True, slots=True)
class RowError:
    """Validation error for one CSV row."""

    row_number: int
    field: str
    value: str
    reason: str
    trade_id: str | None = None

    def __str__(self) -> str:
        trade = f" (trade {self.trade_id})" if self.trade_id else ""

        return(
            f"line {self.row_number}{trade}: "
            f"{self.field}={self.value} - {self.reason}"
        )
