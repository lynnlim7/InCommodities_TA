"""The port the application uses to obtain a trade book.

Stated as a Protocol so the calculation never learns where trades came from. Today the
only implementation reads a CSV; an API feed or a database would satisfy the same
interface without the core or the orchestration changing (requirements.md S14).
"""

from __future__ import annotations

from typing import Protocol

from app.core import TradeBook


class TradeRepository(Protocol):
    """A source of validated trades."""

    @property
    def source(self) -> str:
        """Human-readable description of where the trades come from, for diagnostics."""
        ...

    def load(self) -> TradeBook:
        """Return every trade, or raise.

        Raises:
            TradeSourceError: the source itself is unusable.
            TradeBookValidationError: the source is readable but its records are invalid.

        Because an invalid record fails the whole run (S12), a returned book is always
        complete: records read equals records accepted, and records rejected is zero.
        """
        ...
