"""Position direction labels."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum


class Position(Enum):
    """Whether a net position is long, short, or flat (requirements.md S6.4)."""

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


def classify(net_mwh: Decimal) -> Position:
    """Label a net MWh figure.

    Classification is driven by net MWh, the additive period quantity, so that the label
    can never disagree with the number shown beside it.
    """
    if net_mwh > 0:
        return Position.LONG
    if net_mwh < 0:
        return Position.SHORT
    return Position.FLAT
