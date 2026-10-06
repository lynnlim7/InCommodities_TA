"""CSV boundary.

The repository is the only place untrusted input enters the application:

* a structural problem with the file (missing, unreadable, wrong columns)
  fails the run -- every row is equally untrustworthy;
* a bad row is quarantined with every reason it failed, and the rest of the
  book still loads, so one malformed trade never blinds the desk.

Real files are written with ``tmp_path``. Mocking ``open`` or
``csv.DictReader`` would test the mock, not the CSV dialect handling (BOM,
quoting, blank values) that is the actual risk here.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.models import BuySell, DeliveryPeriod, ReferenceData
from app.infrastructure.csv_repository import CsvTradeRepository
from app.infrastructure.errors import TradeSourceError
from app.infrastructure.schemas import CSV_HEADERS

pytestmark = pytest.mark.integration

HEADER = ",".join(CSV_HEADERS)
VALID_ROW = (
    "T001,2026-09-03,Fuji Utility Services,Tokyo,Futures,Buy,"
    "Oct-26 Base,Base,2026-10-01,2026-11-01,10,15.10"
)
REFERENCE = ReferenceData(
    areas=frozenset({"Tokyo", "Kansai"}),
    trade_types=frozenset({"Futures", "OTC Forwards"}),
    load_profiles=frozenset({"Base", "Peak"}),
)


def write_csv(tmp_path, *lines):
    path = tmp_path / "trades.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load(path):
    return CsvTradeRepository(path=path, reference=REFERENCE).load()


def numbered(row, number):
    """The same row under another trade id."""
    return row.replace("T001", f"T{number:03d}", 1)


# --- Good rows ----------------------------------------------------------------


def test_a_valid_row_is_normalized_onto_the_domain_trade(tmp_path):
    """The repository hands the engine domain objects, not raw CSV rows.

    The two date columns become a single half-open ``DeliveryPeriod``, and
    volume stays ``Decimal`` so no binary rounding enters the position.
    """
    result = load(write_csv(tmp_path, HEADER, VALID_ROW))

    [trade] = result.trade_book
    assert result.rows_read == 1
    assert result.quarantined == ()
    assert trade.trade_id == "T001"
    assert trade.area == "Tokyo"
    assert trade.trade_type == "Futures"
    assert trade.buy_sell is BuySell.BUY
    assert trade.load_profile == "Base"
    assert trade.delivery == DeliveryPeriod(
        start=date(2026, 10, 1),
        end=date(2026, 11, 1),
    )
    assert trade.volume_mw == Decimal("10")
    assert trade.product == "Oct-26 Base"


def test_direction_survives_normalization_as_a_signed_volume(tmp_path):
    sell_row = VALID_ROW.replace(",Futures,Buy,", ",Futures,Sell,")

    [trade] = load(write_csv(tmp_path, HEADER, sell_row)).trade_book

    assert trade.volume_mw_direction == Decimal("-10")


def test_a_padded_direction_is_stripped_like_every_other_field(tmp_path):
    padded = VALID_ROW.replace(",Futures,Buy,", ",Futures, Buy ,")

    [trade] = load(write_csv(tmp_path, HEADER, padded)).trade_book

    assert trade.buy_sell is BuySell.BUY


# --- A broken file fails the run ----------------------------------------------


def test_a_missing_column_fails_the_run(tmp_path):
    """A structural problem is the file's, not one trade's."""
    header = ",".join(field for field in CSV_HEADERS if field != "volume_mw")
    row = ",".join(part for index, part in enumerate(VALID_ROW.split(",")) if index != 10)

    with pytest.raises(TradeSourceError):
        load(write_csv(tmp_path, header, row))


def test_a_missing_file_fails_the_run(tmp_path):
    with pytest.raises(TradeSourceError):
        load(tmp_path / "absent.csv")


# --- A bad row is quarantined; the rest of the book still loads ---------------


def test_one_bad_trade_is_quarantined_and_the_rest_still_load(tmp_path):
    """The case this design exists for: one malformed trade among good ones.

    A negative volume is ambiguous (direction already carries the sign), so
    that trade is set aside with its line, id and field named, and the other
    trade is still counted.
    """
    bad_row = VALID_ROW.replace(",10,15.10", ",-5,15.10")
    path = write_csv(tmp_path, HEADER, bad_row, numbered(VALID_ROW, 2))

    result = load(path)

    assert [trade.trade_id for trade in result.trade_book] == ["T002"]
    [quarantined] = result.quarantined
    [error] = quarantined.errors
    assert quarantined.row_number == 2
    assert error.trade_id == "T001"
    assert error.field == "volume_mw"


def test_a_delivery_period_ending_before_it_starts_is_quarantined(tmp_path):
    bad_row = VALID_ROW.replace("2026-10-01,2026-11-01", "2026-11-01,2026-10-01")

    [quarantined] = load(write_csv(tmp_path, HEADER, bad_row)).quarantined

    assert "start_date must be before end_date" in str(quarantined.errors[0])


@pytest.mark.parametrize("direction", ["buy", "B", "Purchase", ""])
def test_an_unrecognised_direction_is_quarantined(tmp_path, direction):
    """Direction is the sign of the position, so it is parsed, not copied."""
    bad_row = VALID_ROW.replace(",Futures,Buy,", f",Futures,{direction},")

    [quarantined] = load(write_csv(tmp_path, HEADER, bad_row)).quarantined

    [error] = quarantined.errors
    assert error.field == "buy_sell"


@pytest.mark.parametrize(
    ("field", "good", "bad"),
    [
        ("area", ",Tokyo,", ",Toyko,"),
        ("trade_type", ",Futures,", ",Swap,"),
        ("load_profile", ",Base,2026", ",Shoulder,2026"),
    ],
)
def test_unconfigured_reference_data_is_quarantined_with_its_line(
    tmp_path, field, good, bad
):
    """Area, trade type and profile are checked against configuration here,
    so each is reported with its line and trade, like any other bad value."""
    bad_row = VALID_ROW.replace(good, bad, 1)

    [quarantined] = load(write_csv(tmp_path, HEADER, bad_row)).quarantined

    [error] = quarantined.errors
    assert error.field == field
    assert error.trade_id == "T001"


def test_every_copy_of_a_duplicate_trade_id_is_quarantined(tmp_path):
    """Counting both copies would double the position; keeping one is a guess."""
    result = load(write_csv(tmp_path, HEADER, VALID_ROW, VALID_ROW))

    assert len(result.trade_book) == 0
    assert [row.row_number for row in result.quarantined] == [2, 3]
    assert "lines 2, 3" in str(result.quarantined[0].errors[0])


def test_a_row_with_more_values_than_columns_is_quarantined(tmp_path):
    """An unquoted comma shifts every later value into the wrong column."""
    shifted = VALID_ROW.replace("Fuji Utility Services", "Fuji, Utility Services")

    result = load(write_csv(tmp_path, HEADER, shifted))

    assert len(result.trade_book) == 0
    assert len(result.quarantined) == 1


def test_every_problem_in_the_file_is_reported_in_one_pass(tmp_path):
    """The operator should be able to fix the file in one edit."""
    path = write_csv(
        tmp_path,
        HEADER,
        VALID_ROW.replace(",10,15.10", ",-5,15.10"),
        numbered(VALID_ROW, 2).replace(",Tokyo,", ",,"),
    )

    result = load(path)

    assert result.rows_read == 2
    assert [row.row_number for row in result.quarantined] == [2, 3]


# --- What can still be read of a quarantined trade -----------------------------


def test_a_quarantined_trade_keeps_its_area_and_dates_when_readable(tmp_path):
    """A bad volume still says which positions the trade could have moved."""
    bad_row = VALID_ROW.replace(",10,15.10", ",-5,15.10")

    [quarantined] = load(write_csv(tmp_path, HEADER, bad_row)).quarantined

    assert quarantined.excluded.area == "Tokyo"
    assert quarantined.excluded.delivery == DeliveryPeriod(
        start=date(2026, 10, 1),
        end=date(2026, 11, 1),
    )


def test_an_unconfigured_area_is_kept_as_unknown(tmp_path):
    """"Toyko" most likely means Tokyo, so it must mark every area, not none."""
    bad_row = VALID_ROW.replace(",Tokyo,", ",Toyko,")

    [quarantined] = load(write_csv(tmp_path, HEADER, bad_row)).quarantined

    assert quarantined.excluded.area is None


def test_unreadable_dates_leave_the_delivery_unknown(tmp_path):
    bad_row = VALID_ROW.replace("2026-10-01,2026-11-01", "2026-10-01,soon")

    [quarantined] = load(write_csv(tmp_path, HEADER, bad_row)).quarantined

    assert quarantined.excluded.delivery is None
