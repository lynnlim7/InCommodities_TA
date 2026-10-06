"""
Errors raised while loading trade data. 
"""

from __future__ import annotations 

from dataclasses import dataclass

class TradeSourceError(Exception):
    """Trade source cannot be read or has an invalid structure."""

@dataclass(frozen=True, slots=True)
class RowError:
    """"Validation error for one CSV row."""

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

class TradeBookValidationError(Exception):
    """Invalid trade rows in CSV."""

    def __init__(
            self, 
            errors: list[RowError],
            rows_read: int
    ) -> None:
        self.errors = errors
        self.rows_read = rows_read

    def __str__(self) -> str:
        """EReturn a user readable validation report"""
        summary = (
            f"{len(self.errors)} validation error"
            f"in {self.rows_read} row"
        )

        details = "\n".join(
            f" {error}" for error in self.errors
        )

        return f"{summary}\n{details}"
