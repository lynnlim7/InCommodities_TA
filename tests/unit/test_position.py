"""LONG / SHORT / FLAT classification (requirements.md S6.4, AC-12)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core import Position, classify

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("net_mwh", "expected"),
    [
        (Decimal(720), Position.LONG),
        (Decimal("0.0001"), Position.LONG),
        (Decimal(-720), Position.SHORT),
        (Decimal("-0.0001"), Position.SHORT),
        (Decimal(0), Position.FLAT),
        (Decimal("-0.00"), Position.FLAT),
    ],
)
def test_classification_covers_positive_negative_and_zero(
    net_mwh: Decimal, expected: Position
) -> None:
    assert classify(net_mwh) is expected
