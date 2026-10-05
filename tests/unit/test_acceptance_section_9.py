"""The expected results in requirements.md S9, row for row (AC-09, AC-10, AC-11).

This is the acceptance check for the calculation itself, run against a book built in
memory so it exercises no filesystem and no CSV parser (S13.3). M5 repeats the same
assertions through the real CSV end to end.

Net MWh is compared exactly. Average MW is compared after rounding to two decimal places,
because S9 presents repeating averages rounded for readability -- the unrounded value is
asserted separately in test_engine.py.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from app.core import Granularity, PositionViews, calculate_views
from tests.builders import AS_OF, supplied_book
from tests.expected import SECTION_9_1_DAILY, SECTION_9_2_WEEKLY, SECTION_9_3_MONTHLY
from tests.expected import Row as ExpectedRow

pytestmark = pytest.mark.unit

TWO_PLACES = Decimal("0.01")

EXPECTED: dict[Granularity, tuple[ExpectedRow, ...]] = {
    Granularity.DAILY: SECTION_9_1_DAILY,
    Granularity.WEEKLY: SECTION_9_2_WEEKLY,
    Granularity.MONTHLY: SECTION_9_3_MONTHLY,
}


@pytest.fixture(scope="module")
def views() -> PositionViews:
    return calculate_views(supplied_book(), AS_OF)


@pytest.mark.parametrize("granularity", list(Granularity), ids=lambda g: g.value)
def test_view_has_the_documented_number_of_rows(
    views: PositionViews, granularity: Granularity
) -> None:
    assert len(views[granularity]) == len(EXPECTED[granularity])


@pytest.mark.parametrize(
    ("granularity", "index"),
    [(g, i) for g, rows in EXPECTED.items() for i in range(len(rows))],
    ids=[
        f"{g.value}-{rows[i][0]}-{rows[i][1]}"
        for g, rows in EXPECTED.items()
        for i in range(len(rows))
    ],
)
def test_row_matches_the_specification(
    views: PositionViews, granularity: Granularity, index: int
) -> None:
    label, area, expected_average_mw, expected_net_mwh, expected_position = EXPECTED[granularity][
        index
    ]
    row = views[granularity].rows[index]

    assert (row.period.label, row.area) == (label, area)
    assert row.net_mwh == Decimal(expected_net_mwh)
    assert row.average_mw.quantize(TWO_PLACES, rounding=ROUND_HALF_UP) == Decimal(
        expected_average_mw
    )
    assert row.position.value == expected_position


def test_the_run_reports_its_as_of_date_and_areas(views: PositionViews) -> None:
    """S8.1: the view must state its as-of date and the areas it covered."""
    assert views.as_of == AS_OF
    assert views.areas == ("Tokyo", "Kansai")
    assert views.row_counts == {"daily": 14, "weekly": 8, "monthly": 24}
