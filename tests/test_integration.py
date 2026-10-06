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
from app.core.errors import UnsupportedTradeTypeError
from app.core.periods import monthly_periods
from app.core.profiles import ContinuousProfile, ProfileRegistry
from app.dashboard.snapshot import load_snapshot
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
        supported_trade_types=frozenset({"Futures"}),
    )

    position = position_for(positions, area="Tokyo", period=october[0])
    assert position.period.label == "Oct-26"
    assert position.net_position_mw == Decimal("10")
    assert position.net_position_mwh == Decimal("7440")


def test_the_shipped_book_reports_the_hand_checked_tokyo_october_position():
    """The real trade book and configuration, end to end, through the snapshot.

    Tokyo October is +30 MW from Cal-26, Q4-26 and Oct-26, plus the Week-42
    buy (+10 MW for 168 hours) and the weekend sell (-8 MW for 48 hours):
    (30 x 744 + 10 x 168 - 8 x 48) / 744 MW. Its hours range from +22 MW
    (the sold weekend) to +40 MW (week 42).
    """
    snapshot = load_snapshot(as_of=date(2026, 10, 1))
    october = next(
        period
        for view in snapshot.views
        for period in view.periods
        if period.label == "Oct-26"
    )

    position = snapshot.position(area="Tokyo", period=october)

    assert position.net_position_mwh == Decimal("23616")
    assert position.net_position_mw == Decimal("23616") / Decimal("744")
    assert position.exposure.min_mw == Decimal("22")
    assert position.exposure.max_mw == Decimal("40")


def test_a_trade_type_missing_from_the_configuration_fails_the_snapshot(tmp_path):
    """The shipped trade_types.yaml is what a book is checked against.

    A "Swap" read from file, with a valid area and profile, still stops the
    snapshot: the configuration lists Futures and OTC Forwards only.
    """
    path = tmp_path / "trades.csv"
    path.write_text(
        ",".join(CSV_HEADERS)
        + "\n"
        + "T001,2026-09-03,Fuji Utility Services,Tokyo,Swap,Buy,"
        "Oct-26 Base,Base,2026-10-01,2026-11-01,10,15.10\n",
        encoding="utf-8",
    )

    with pytest.raises(UnsupportedTradeTypeError):
        load_snapshot(as_of=date(2026, 10, 1), trades_csv=path)
