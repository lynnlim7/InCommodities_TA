"""One lightweight integration test across ingestion and calculation.

It proves the whole pipeline composes: a real CSV on disk, read and normalized
by the real repository, reported over a real generated reporting period, gives
the expected position. Every step is covered in isolation elsewhere; this test
exists only to catch the seams between them.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.calculations import calculate_positions
from app.core.periods import monthly_periods
from app.core.profiles import ContinuousProfile, ProfileRegistry
from app.infrastructure.csv_repository import CsvTradeRepository
from app.infrastructure.schemas import CSV_HEADERS
from tests.helpers import position_for

pytestmark = pytest.mark.integration


def test_a_csv_buy_becomes_a_long_october_position(tmp_path):
    """Tokyo, Buy 10 MW Base for October, read from file, reports +10 MW."""
    path = tmp_path / "trades.csv"
    path.write_text(
        ",".join(CSV_HEADERS)
        + "\n"
        + "T001,2026-09-03,Fuji Utility Services,Tokyo,Futures,Buy,"
        "Oct-26 Base,Base,2026-10-01,2026-11-01,10,15.10\n",
        encoding="utf-8",
    )

    trade_book = CsvTradeRepository(path=path).load()
    october = monthly_periods(as_of=date(2026, 10, 1), count=1)

    positions = calculate_positions(
        trade_book=trade_book,
        periods=october,
        profiles=ProfileRegistry(profiles={"Base": ContinuousProfile()}),
        supported_areas=frozenset({"Tokyo"}),
    )

    position = position_for(
        positions, area="Tokyo", load_profile="Base", period=october[0]
    )
    assert position.period.label == "Oct-26"
    assert position.net_position_mw == Decimal("10")
