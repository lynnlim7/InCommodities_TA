"""The untrusted input boundary: one CSV row, validated into domain values.

This is the only place in the application where external strings are turned into typed
values (requirements.md AC-02). Everything downstream receives a ``Trade``, by which point
every invariant in S5 already holds.

Field-level validators delegate to the domain's own parsers -- ``Direction.parse``,
``parse_profile``, ``parse_trade_type`` -- so the set of acceptable values is defined once,
in the domain, and registering a new load profile or trade type needs no change here
(S3.2, AC-19). Those parsers raise ``ValueError`` subclasses, which Pydantic captures and
attributes to the field that produced them, giving AC-14's field-level reporting for free.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from app.core import (
    DateInterval,
    Direction,
    Trade,
    parse_profile,
    parse_trade_type,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""A required text field. Whitespace is stripped first, so "   " is empty (S5.3)."""

CSV_HEADERS: tuple[str, ...] = (
    "trade_id",
    "trade_date",
    "counterparty",
    "area",
    "trade_type",
    "buy_sell",
    "product",
    "load_profile",
    "start_date",
    "end_date",
    "volume_mw",
    "price_jpy_kwh",
)
"""The columns the supplied file provides (S4.1). Order is for reporting, not parsing."""


class RawTradeRow(BaseModel):
    """One validated CSV row.

    Declared in CSV column order because ``end_date`` is validated against ``start_date``
    and Pydantic exposes earlier fields to later validators only in declaration order.
    """

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    trade_id: NonEmptyText
    trade_date: date
    counterparty: NonEmptyText
    area: NonEmptyText
    trade_type: NonEmptyText
    buy_sell: Direction
    product: NonEmptyText
    load_profile: NonEmptyText
    start_date: date
    end_date: date
    volume_mw: Decimal = Field(gt=0)
    """Strictly positive: direction carries the sign, so a negative volume would be a
    second, conflicting way to express a short position (S5.2)."""

    price_jpy_kwh: Decimal = Field(gt=0)
    """Validated and retained, but never used in the physical position (S4.3, AC-17)."""

    @field_validator("buy_sell", mode="before")
    @classmethod
    def _parse_direction(cls, value: object) -> object:
        return Direction.parse(value) if isinstance(value, str) else value

    @field_validator("trade_type")
    @classmethod
    def _recognise_trade_type(cls, value: str) -> str:
        """Validated metadata with no position effect: every current type delivers
        identically (S4.3, S5.3). Checked so an unrecognised contract type surfaces
        rather than being silently positioned as though it were a future."""
        return parse_trade_type(value)

    @field_validator("load_profile")
    @classmethod
    def _recognise_load_profile(cls, value: str) -> str:
        """Resolved to prove a covered-hour rule exists, then stored by canonical name.

        An unregistered profile is rejected rather than defaulted to Base, because
        treating an unknown shape as baseload would overstate delivered volume.
        """
        return parse_profile(value).name

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, value: date, info: ValidationInfo) -> date:
        """S5.1: end_date is exclusive, so it must be strictly after start_date.

        Checked on ``end_date`` rather than in a whole-model validator so the error is
        attributed to a named field, which is what makes the message actionable.
        """
        start = info.data.get("start_date")
        if start is not None and start >= value:
            raise ValueError(
                f"end_date must be after start_date {start.isoformat()}; end_date is "
                f"exclusive (the day after the last delivery day), so an equal or "
                f"earlier value delivers nothing"
            )
        return value

    def to_trade(self) -> Trade:
        """Build the domain object. Every invariant has already been checked above."""
        return Trade(
            trade_id=self.trade_id,
            trade_date=self.trade_date,
            counterparty=self.counterparty,
            area=self.area,
            trade_type=self.trade_type,
            direction=self.buy_sell,
            product=self.product,
            profile=parse_profile(self.load_profile),
            interval=DateInterval(self.start_date, self.end_date),
            volume_mw=self.volume_mw,
            price_jpy_kwh=self.price_jpy_kwh,
        )
