"""Trade direction and its sign convention."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from app.core.errors import UnsupportedDirectionError


class Direction(Enum):
    """Whether a trade was bought or sold.

    Sign convention (requirements.md S5.2): Buy is positive and long, Sell is negative
    and short. Direction carries the sign so that ``volume_mw`` can stay strictly
    positive and there is exactly one way to express a short position.
    """

    BUY = "Buy"
    SELL = "Sell"

    @property
    def sign(self) -> Decimal:
        """+1 for Buy, -1 for Sell."""
        return Decimal(1) if self is Direction.BUY else Decimal(-1)

    @classmethod
    def parse(cls, raw: str) -> Direction:
        """Convert an external buy/sell string into a Direction.

        Matching is case-insensitive and whitespace-tolerant; anything else is rejected
        rather than guessed at (requirements.md S5.3, S12).
        """
        try:
            return _BY_NAME[raw.strip().casefold()]
        except KeyError:
            supported = ", ".join(d.value for d in cls)
            raise UnsupportedDirectionError(
                f"unsupported buy_sell value {raw!r}; supported values are: {supported}"
            ) from None


_BY_NAME: dict[str, Direction] = {d.value.casefold(): d for d in Direction}
