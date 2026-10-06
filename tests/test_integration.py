"""Integration tests across ingestion, calculation and the snapshot.

They prove the pipeline composes: a real CSV on disk, read by the real
repository, reported over real generated periods, gives the expected
position -- and a bad trade is quarantined and surfaced rather than either
stopping the run or vanishing.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.calculations import calculate_positions
from app.core.models import ReferenceData
from app.core.periods import monthly_periods
from app.core.profiles import ContinuousProfile, ProfileRegistry
from app.dashboard.snapshot import load_snapshot
from app.infrastructure.csv_repository import CsvTradeRepository
from app.infrastructure.errors import TradeSourceError
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

    trade_book = CsvTradeRepository(
        path=path,
        reference=ReferenceData(
            areas=frozenset({"Tokyo"}),
            trade_types=frozenset({"Futures"}),
            load_profiles=frozenset({"Base"}),
        ),
    ).load().trade_book
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



GOOD_TOKYO_OCT = (
    "T001,2026-09-03,Fuji Utility Services,Tokyo,Futures,Buy,"
    "Oct-26 Base,Base,2026-10-01,2026-11-01,10,15.10"
)


def write_book(tmp_path, *rows):
    path = tmp_path / "trades.csv"
    path.write_text(
        "\n".join((",".join(CSV_HEADERS), *rows)) + "\n",
        encoding="utf-8",
    )
    return path


def period_labelled(snapshot, label):
    return next(
        period
        for view in snapshot.views
        for period in view.periods
        if period.label == label
    )


def test_one_bad_trade_is_quarantined_and_only_its_positions_are_incomplete(tmp_path):
    """A Swap is not a configured trade type, so it is quarantined.

    The run does not fail: Tokyo October still reports the good trade, and
    only the positions the Swap could have moved -- Tokyo November -- are
    marked incomplete. Kansai, and Tokyo's other months, stay complete.
    """
    path = write_book(
        tmp_path,
        GOOD_TOKYO_OCT,
        "T002,2026-09-03,Fuji Utility Services,Tokyo,Swap,Buy,"
        "Nov-26 Base,Base,2026-11-01,2026-12-01,10,15.10",
    )

    snapshot = load_snapshot(as_of=date(2026, 10, 1), trades_csv=path)

    [quarantined] = snapshot.load_result.excluded_trades
    assert quarantined.trade_id == "T002"

    october = period_labelled(snapshot, "Oct-26")
    november = period_labelled(snapshot, "Nov-26")
    assert snapshot.position(area="Tokyo", period=october).net_position_mw == Decimal("10")
    assert snapshot.excluded_trades(area="Tokyo", period=october) == ()
    assert snapshot.excluded_trades(area="Tokyo", period=november) == (quarantined,)
    assert snapshot.excluded_trades(area="Kansai", period=november) == ()


def test_a_broken_file_still_fails_the_run(tmp_path):
    """Fail closed: a structural problem leaves nothing trustworthy to show."""
    path = tmp_path / "trades.csv"
    path.write_text("not,a,trade,book\n1,2,3,4\n", encoding="utf-8")

    with pytest.raises(TradeSourceError):
        load_snapshot(as_of=date(2026, 10, 1), trades_csv=path)
