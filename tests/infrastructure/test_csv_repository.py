"""CSV boundary.

The repository is the only place untrusted input enters the application, and
the stated policy is that an invalid book fails the run rather than producing
a partial position -- a position quietly missing trades looks complete and can
imply the wrong hedge. These tests pin that policy and the typing the domain
depends on.

Real files are written with ``tmp_path``. Mocking ``open`` or
``csv.DictReader`` would test the mock, not the CSV dialect handling (BOM,
quoting, blank values) that is the actual risk here.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.models import BuySell, DeliveryPeriod
from app.infrastructure.csv_repository import CsvTradeRepository
from app.infrastructure.errors import TradeBookValidationError, TradeSourceError
from app.infrastructure.schemas import CSV_HEADERS

pytestmark = pytest.mark.integration

HEADER = ",".join(CSV_HEADERS)
VALID_ROW = (
    "T001,2026-09-03,Fuji Utility Services,Tokyo,Futures,Buy,"
    "Oct-26 Base,Base,2026-10-01,2026-11-01,10,15.10"
)


def write_csv(tmp_path, *lines):
    path = tmp_path / "trades.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_a_valid_row_is_normalized_onto_the_domain_trade(tmp_path):
    """The repository hands the engine domain objects, not raw CSV rows.

    This pins the whole mapping, because every field is one the position
    depends on: the two date columns become a single half-open
    ``DeliveryPeriod``, and volume stays ``Decimal`` -- the engine multiplies
    it by hours, so a float here would reintroduce binary rounding into the
    position.
    """
    path = write_csv(tmp_path, HEADER, VALID_ROW)

    trade_book = CsvTradeRepository(path=path).load()

    [trade] = trade_book
    assert len(trade_book) == 1
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


def test_direction_survives_normalization_as_a_signed_volume(tmp_path):
    """A Sell row reaches the engine already carrying its sign.

    Direction is parsed at the boundary and read as a sign by the engine, so
    the two steps are checked to meet: nothing in between re-interprets it.
    """
    sell_row = VALID_ROW.replace(",Futures,Buy,", ",Futures,Sell,")
    path = write_csv(tmp_path, HEADER, sell_row)

    [trade] = CsvTradeRepository(path=path).load()

    assert trade.buy_sell is BuySell.SELL
    assert trade.volume_mw_direction == Decimal("-10")


def test_a_missing_column_fails_the_source_before_any_row_is_read(tmp_path):
    """A structural problem is the operator's, not the trade's.

    It is reported as a source error with no row numbers, because every row is
    equally unreadable and naming them would be noise.
    """
    header = ",".join(field for field in CSV_HEADERS if field != "volume_mw")
    row = ",".join(part for index, part in enumerate(VALID_ROW.split(",")) if index != 10)
    path = write_csv(tmp_path, header, row)

    with pytest.raises(TradeSourceError):
        CsvTradeRepository(path=path).load()


def test_a_missing_file_is_reported_as_a_source_error(tmp_path):
    with pytest.raises(TradeSourceError):
        CsvTradeRepository(path=tmp_path / "absent.csv").load()


def test_an_invalid_volume_fails_the_whole_run_and_names_the_field(tmp_path):
    """A negative volume is rejected rather than read as a short.

    Direction already carries the sign, so a negative volume is ambiguous and
    is treated as bad data.
    """
    bad_row = VALID_ROW.replace(",10,15.10", ",-5,15.10")
    path = write_csv(tmp_path, HEADER, bad_row)

    with pytest.raises(TradeBookValidationError) as raised:
        CsvTradeRepository(path=path).load()

    [error] = raised.value.errors
    assert error.row_number == 2
    assert error.trade_id == "T001"
    assert error.field == "volume_mw"


def test_a_delivery_period_ending_before_it_starts_is_rejected(tmp_path):
    """The half-open interval rule is enforced at the boundary too.

    The domain's ``DeliveryPeriod`` would also reject it, but failing here
    lets the error name the file, line and trade the operator has to fix.
    """
    bad_row = VALID_ROW.replace("2026-10-01,2026-11-01", "2026-11-01,2026-10-01")
    path = write_csv(tmp_path, HEADER, bad_row)

    with pytest.raises(TradeBookValidationError) as raised:
        CsvTradeRepository(path=path).load()

    assert "start_date must be before end_date" in str(raised.value)


def test_a_duplicate_trade_id_is_rejected(tmp_path):
    """Two rows with one id mean an unresolvable book.

    Either is a genuine second trade that was mis-keyed, or a restatement of
    the first; summing both would double the position and dropping one would
    halve it, so neither is guessed at.
    """
    path = write_csv(tmp_path, HEADER, VALID_ROW, VALID_ROW)

    with pytest.raises(TradeBookValidationError) as raised:
        CsvTradeRepository(path=path).load()

    assert any(error.field == "trade_id" for error in raised.value.errors)


def test_every_problem_in_the_file_is_reported_in_one_pass(tmp_path):
    """The operator should be able to fix the file in one edit.

    Failing on the first bad row would mean one run per defect.
    """
    path = write_csv(
        tmp_path,
        HEADER,
        VALID_ROW.replace(",10,15.10", ",-5,15.10"),
        VALID_ROW.replace("T001", "T002").replace(",Tokyo,", ",,"),
    )

    with pytest.raises(TradeBookValidationError) as raised:
        CsvTradeRepository(path=path).load()

    assert raised.value.rows_read == 2
    assert {error.row_number for error in raised.value.errors} == {2, 3}


@pytest.mark.parametrize("direction", ["buy", "B", "Purchase", ""])
def test_an_unrecognised_direction_is_rejected_at_the_boundary(tmp_path, direction):
    """Direction is the sign of the position, so it is parsed, not copied.

    Accepting the raw string would push the failure past validation into the
    calculation, where it surfaces as a bare ValueError outside the one-pass
    report and names neither the line nor the trade. One representative set of
    near-misses is tested, not every possible string.
    """
    bad_row = VALID_ROW.replace(",Futures,Buy,", f",Futures,{direction},")
    path = write_csv(tmp_path, HEADER, bad_row)

    with pytest.raises(TradeBookValidationError) as raised:
        CsvTradeRepository(path=path).load()

    [error] = raised.value.errors
    assert error.row_number == 2
    assert error.field == "buy_sell"


def test_a_padded_direction_is_stripped_like_every_other_field(tmp_path):
    """Spaces after commas are ordinary in a hand-edited CSV.

    Every other column is whitespace-stripped, so direction is too. Rejecting
    " Buy " while accepting " Tokyo " would be an inconsistency the operator
    has no way to predict.
    """
    padded = VALID_ROW.replace(",Futures,Buy,", ",Futures, Buy ,")
    path = write_csv(tmp_path, HEADER, padded)

    [trade] = CsvTradeRepository(path=path).load()

    assert trade.buy_sell is BuySell.BUY


def test_the_descriptive_product_label_is_carried_through_to_the_domain(tmp_path):
    """The product name reaches the trade so a drill-down can name the deal.

    It stays descriptive metadata: delivery comes from ``start_date``,
    ``end_date`` and ``load_profile``, and nothing parses this string. It is
    carried only because a trader recognises "Oct-26 Base" faster than a
    trade id when checking which deals produced a position.
    """
    path = write_csv(tmp_path, HEADER, VALID_ROW)

    [trade] = CsvTradeRepository(path=path).load()

    assert trade.product == "Oct-26 Base"
