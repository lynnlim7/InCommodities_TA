"""The trade entity and the book of trades.

A Trade is immutable and fully typed: by the time one exists, every invariant in
requirements.md S5 holds. Downstream code therefore never re-validates, and the position
engine can be a plain summation.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.config import area_sort_key
from app.core.direction import Direction
from app.core.errors import (
    DuplicateTradeIdError,
    InvalidPriceError,
    InvalidVolumeError,
    MissingValueError,
    UnsupportedTradeTypeError,
)
from app.core.interval import DateInterval
from app.core.profiles import LoadProfile

KNOWN_TRADE_TYPES: tuple[str, ...] = ("Futures",)
"""Trade types the application recognises.

Trade type is validated metadata with no effect on the delivery position: every current
value is treated identically (requirements.md S4.3, S5.3). It is checked anyway so an
unrecognised contract type surfaces as an error instead of being silently positioned as
though it were a future. OTC forwards would be added here once their position semantics
are agreed -- the brief defines none, so none are invented (S3.2).
"""

_TRADE_TYPES: dict[str, str] = {t.casefold(): t for t in KNOWN_TRADE_TYPES}


def register_trade_type(trade_type: str) -> None:
    """Make a trade type acceptable to parsing."""
    _TRADE_TYPES[trade_type.casefold()] = trade_type


def parse_trade_type(raw: str) -> str:
    """Resolve an external trade_type string to its canonical spelling."""
    try:
        return _TRADE_TYPES[raw.strip().casefold()]
    except KeyError:
        supported = ", ".join(sorted(_TRADE_TYPES.values()))
        raise UnsupportedTradeTypeError(
            f"unsupported trade_type {raw!r}; recognised types are: {supported}"
        ) from None


@dataclass(frozen=True, slots=True)
class Trade:
    """A single booked trade.

    Fields that drive the position (area, direction, profile, interval, volume) sit
    alongside retained metadata (counterparty, product, price). The metadata is validated
    and carried but never read by the calculation, which is what makes AC-16 and AC-17 --
    product text and price cannot change a position -- true by construction rather than
    by convention.
    """

    trade_id: str
    trade_date: date
    counterparty: str
    area: str
    trade_type: str
    direction: Direction
    product: str
    profile: LoadProfile
    interval: DateInterval
    volume_mw: Decimal
    price_jpy_kwh: Decimal

    def __post_init__(self) -> None:
        for field_name in ("trade_id", "counterparty", "area", "trade_type", "product"):
            value: str = getattr(self, field_name)
            if not value.strip():
                raise MissingValueError(f"{field_name} must not be empty")

        # Volume is strictly positive because Direction already carries the sign. Allowing
        # a negative volume would create a second way to express a short and make the two
        # representations disagree (requirements.md S5.2).
        if self.volume_mw <= 0:
            raise InvalidVolumeError(
                f"volume_mw must be strictly positive, got {self.volume_mw}; "
                f"use buy_sell=Sell to express a short position, not a negative volume"
            )

        if self.price_jpy_kwh <= 0:
            raise InvalidPriceError(
                f"price_jpy_kwh must be strictly positive, got {self.price_jpy_kwh}"
            )

    @property
    def signed_mw(self) -> Decimal:
        """Volume with the direction applied: positive for Buy, negative for Sell."""
        return self.direction.sign * self.volume_mw

    def mwh_in(self, period: DateInterval) -> Decimal:
        """Signed MWh this trade delivers inside ``period``.

        This is requirements.md S6.1 verbatim: signed MW times the hours that lie both in
        the delivery/reporting overlap and inside the load profile. A trade that does not
        overlap contributes exactly zero.
        """
        overlap = self.interval.intersection(period)
        if overlap is None:
            return Decimal(0)
        return self.signed_mw * self.profile.covered_hours(overlap)


@dataclass(frozen=True, slots=True)
class TradeBook:
    """An immutable set of trades with unique identities.

    Holding the duplicate-identity check here means it is enforced for any source of
    trades -- CSV today, an API or database later -- rather than only for the CSV reader.
    """

    trades: tuple[Trade, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        duplicates: list[str] = []
        for trade in self.trades:
            if trade.trade_id in seen:
                duplicates.append(trade.trade_id)
            seen.add(trade.trade_id)
        if duplicates:
            # Rejected rather than deduplicated: two rows with one id mean the book is
            # ambiguous, and quietly dropping one could halve a real position (S5.3).
            listed = ", ".join(sorted(set(duplicates)))
            raise DuplicateTradeIdError(f"duplicate trade_id values: {listed}")

    @property
    def observed_areas(self) -> tuple[str, ...]:
        """Distinct delivery areas present, in canonical display order.

        Driven by the book rather than by configuration so that a trader can tell FLAT
        apart from missing output for exactly the areas they actually trade (S8.2, AC-13).
        """
        return tuple(sorted({t.area for t in self.trades}, key=area_sort_key))

    @property
    def horizon(self) -> DateInterval | None:
        """The interval spanned by all delivery periods, or None for an empty book.

        Lets callers discard trades that cannot touch a reporting window at all before
        doing per-period work.
        """
        if not self.trades:
            return None
        return DateInterval(
            start=min(t.interval.start for t in self.trades),
            end=max(t.interval.end for t in self.trades),
        )

    def __len__(self) -> int:
        return len(self.trades)

    def __iter__(self) -> Iterator[Trade]:
        return iter(self.trades)
