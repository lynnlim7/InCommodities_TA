"""CSV to typed trades, and every failure mode S12 enumerates (AC-02, AC-14, AC-15)."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from app.core import Direction, Granularity, TradeBook, calculate_views
from app.infrastructure import (
    CSV_HEADERS,
    DEFAULT_TRADES_CSV,
    CsvTradeRepository,
    RowError,
    TradeBookValidationError,
    TradeSourceError,
)
from tests.builders import AS_OF, supplied_book
from tests.expected import SECTION_9_1_DAILY

pytestmark = pytest.mark.integration

VALID_ROW: dict[str, str] = {
    "trade_id": "T001",
    "trade_date": "2026-09-10",
    "counterparty": "Sakura Power Trading",
    "area": "Tokyo",
    "trade_type": "Futures",
    "buy_sell": "Buy",
    "product": "Oct-26 Base",
    "load_profile": "Base",
    "start_date": "2026-10-01",
    "end_date": "2026-11-01",
    "volume_mw": "20",
    "price_jpy_kwh": "13.50",
}


def write_csv(path: Path, rows: list[dict[str, str]], headers: list[str] | None = None) -> Path:
    """Write a CSV whose columns default to the documented schema.

    Uses the csv module so values containing commas are quoted, as a real export would
    be. Writing them raw would produce a genuinely malformed row and test the wrong thing.
    """
    columns = headers if headers is not None else list(CSV_HEADERS)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows([row.get(column, "") for column in columns] for row in rows)
    return path


def load(path: Path) -> TradeBook:
    return CsvTradeRepository(path).load()


class TestSuppliedFile:
    def test_the_packaged_csv_exists(self) -> None:
        assert DEFAULT_TRADES_CSV.is_file(), "the supplied book ships with the package"

    def test_parses_into_twelve_typed_trades(self) -> None:
        """AC-02: dates, directions, numbers, areas, types, and profiles become types."""
        book = load(DEFAULT_TRADES_CSV)

        assert len(book) == 12
        assert {t.trade_id for t in book} == {f"T{n:03d}" for n in range(1, 13)}
        assert all(isinstance(t.volume_mw, Decimal) for t in book)
        assert all(t.profile.name == "Base" for t in book)
        assert all(t.trade_type == "Futures" for t in book)
        assert {t.direction for t in book} == {Direction.BUY, Direction.SELL}

    def test_matches_the_book_transcribed_in_the_test_builders(self) -> None:
        """Closes the loop: the in-memory fixture the core tests use is the real file.

        Without this, a drifting transcription would let the unit tests pass against a
        book that no longer resembles the supplied data.
        """
        assert load(DEFAULT_TRADES_CSV) == supplied_book()

    def test_observed_facts_match_the_specification(self) -> None:
        """S4.2 records these properties of the supplied book."""
        book = load(DEFAULT_TRADES_CSV)

        assert sum(1 for t in book if t.area == "Tokyo") == 10
        assert sum(1 for t in book if t.area == "Kansai") == 2
        assert book.observed_areas == ("Tokyo", "Kansai")
        assert book.horizon is not None
        assert book.horizon.start.isoformat() == "2026-01-01"
        assert book.horizon.end.isoformat() == "2028-04-01"

    def test_reading_the_file_reproduces_the_expected_daily_view(self) -> None:
        """CSV through to results, so parsing and calculation agree (AC-09)."""
        views = calculate_views(load(DEFAULT_TRADES_CSV), AS_OF)

        actual = [(r.period.label, r.area, int(r.net_mwh)) for r in views[Granularity.DAILY]]
        assert actual == [(label, area, mwh) for label, area, _, mwh, _ in SECTION_9_1_DAILY]

    def test_loading_twice_produces_identical_books(self) -> None:
        """AC-01: every valid record is loaded exactly once, repeatably."""
        assert load(DEFAULT_TRADES_CSV) == load(DEFAULT_TRADES_CSV)

    def test_a_byte_order_mark_does_not_corrupt_the_first_column(self, tmp_path: Path) -> None:
        """Spreadsheet exports commonly add one; it would otherwise break trade_id."""
        target = tmp_path / "bom.csv"
        target.write_bytes(b"\xef\xbb\xbf" + DEFAULT_TRADES_CSV.read_bytes())

        assert load(target) == load(DEFAULT_TRADES_CSV)


class TestSourceFailures:
    """Problems with the file itself: no row-level detail exists to report (S12)."""

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(TradeSourceError, match="not found"):
            load(tmp_path / "absent.csv")

    def test_directory_instead_of_file(self, tmp_path: Path) -> None:
        with pytest.raises(TradeSourceError, match="directory"):
            load(tmp_path)

    def test_empty_file(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.csv"
        target.write_text("", encoding="utf-8")

        with pytest.raises(TradeSourceError, match="no header row"):
            load(target)

    def test_missing_required_column(self, tmp_path: Path) -> None:
        headers = [h for h in CSV_HEADERS if h != "volume_mw"]
        target = write_csv(tmp_path / "short.csv", [VALID_ROW], headers=headers)

        with pytest.raises(TradeSourceError, match="missing columns: volume_mw"):
            load(target)

    def test_unexpected_column(self, tmp_path: Path) -> None:
        target = write_csv(
            tmp_path / "extra.csv", [VALID_ROW], headers=[*CSV_HEADERS, "pnl_jpy"]
        )

        with pytest.raises(TradeSourceError, match="unexpected columns: pnl_jpy"):
            load(target)

    def test_duplicate_column(self, tmp_path: Path) -> None:
        target = write_csv(tmp_path / "dupe.csv", [VALID_ROW], headers=[*CSV_HEADERS, "area"])

        with pytest.raises(TradeSourceError, match="duplicate columns: area"):
            load(target)

    def test_header_only_file_yields_an_empty_book(self, tmp_path: Path) -> None:
        """A valid file with no trades is not an error; it is a flat book."""
        target = write_csv(tmp_path / "headers.csv", [])

        assert len(load(target)) == 0


class TestRowFailures:
    """Problems inside otherwise readable rows. Each must name field, value, and reason."""

    def _single_error(self, tmp_path: Path, **overrides: str) -> RowError:
        target = write_csv(tmp_path / "row.csv", [{**VALID_ROW, **overrides}])
        with pytest.raises(TradeBookValidationError) as exc:
            load(target)
        report = exc.value.report
        assert len(report.errors) == 1, report
        return report.errors[0]

    @pytest.mark.parametrize(
        "field", ["trade_id", "counterparty", "area", "trade_type", "product", "load_profile"]
    )
    def test_empty_required_field(self, tmp_path: Path, field: str) -> None:
        error = self._single_error(tmp_path, **{field: ""})

        assert error.field == field

    def test_whitespace_only_field_counts_as_empty(self, tmp_path: Path) -> None:
        error = self._single_error(tmp_path, area="   ")

        assert error.field == "area"

    @pytest.mark.parametrize("value", ["2026-13-01", "01/10/2026", "not-a-date", ""])
    def test_invalid_date_format(self, tmp_path: Path, value: str) -> None:
        error = self._single_error(tmp_path, start_date=value)

        assert error.field == "start_date"
        assert error.value == (repr(value) if not value.strip() else value)

    def test_start_date_equal_to_end_date(self, tmp_path: Path) -> None:
        error = self._single_error(tmp_path, start_date="2026-10-01", end_date="2026-10-01")

        assert error.field == "end_date"
        assert "exclusive" in error.reason

    def test_start_date_after_end_date(self, tmp_path: Path) -> None:
        error = self._single_error(tmp_path, start_date="2026-11-01", end_date="2026-10-01")

        assert error.field == "end_date"
        assert "2026-11-01" in error.reason

    @pytest.mark.parametrize("value", ["Short", "B", "purchase", ""])
    def test_unsupported_buy_sell(self, tmp_path: Path, value: str) -> None:
        error = self._single_error(tmp_path, buy_sell=value)

        assert error.field == "buy_sell"

    def test_unsupported_load_profile_names_what_is_registered(self, tmp_path: Path) -> None:
        error = self._single_error(tmp_path, load_profile="Peak")

        assert error.field == "load_profile"
        assert "Peak" in error.reason and "Base" in error.reason

    def test_unsupported_trade_type(self, tmp_path: Path) -> None:
        error = self._single_error(tmp_path, trade_type="Swap")

        assert error.field == "trade_type"
        assert "Futures" in error.reason

    @pytest.mark.parametrize("value", ["abc", "20MW", "1,000", "1 000", ""])
    def test_non_numeric_volume(self, tmp_path: Path, value: str) -> None:
        error = self._single_error(tmp_path, volume_mw=value)

        assert error.field == "volume_mw"

    @pytest.mark.parametrize("value", ["0", "-5", "-0.1"])
    def test_non_positive_volume(self, tmp_path: Path, value: str) -> None:
        error = self._single_error(tmp_path, volume_mw=value)

        assert error.field == "volume_mw"
        assert error.value == value

    @pytest.mark.parametrize("value", ["abc", "0", "-1.5"])
    def test_invalid_price(self, tmp_path: Path, value: str) -> None:
        error = self._single_error(tmp_path, price_jpy_kwh=value)

        assert error.field == "price_jpy_kwh"

    def test_row_with_too_many_fields(self, tmp_path: Path) -> None:
        target = tmp_path / "wide.csv"
        target.write_text(
            ",".join(CSV_HEADERS) + "\n" + ",".join([*VALID_ROW.values(), "surplus"]) + "\n",
            encoding="utf-8",
        )

        with pytest.raises(TradeBookValidationError) as exc:
            load(target)

        assert "more fields" in exc.value.report.errors[0].reason


class TestDuplicateIdentity:
    def test_duplicate_trade_id_is_rejected(self, tmp_path: Path) -> None:
        """AC-15: rejected explicitly rather than silently deduplicated."""
        target = write_csv(
            tmp_path / "dupes.csv",
            [VALID_ROW, {**VALID_ROW, "volume_mw": "99"}],
        )

        with pytest.raises(TradeBookValidationError) as exc:
            load(target)

        errors = exc.value.report.errors
        assert len(errors) == 1
        assert errors[0].field == "trade_id"
        assert errors[0].trade_id == "T001"
        assert errors[0].row_number == 3, "the repeat is reported, pinpointed by line"
        assert "already used on line 2" in errors[0].reason

    def test_every_duplicated_id_is_reported(self, tmp_path: Path) -> None:
        target = write_csv(
            tmp_path / "dupes.csv",
            [
                VALID_ROW,
                VALID_ROW,
                {**VALID_ROW, "trade_id": "T002"},
                {**VALID_ROW, "trade_id": "T002"},
                {**VALID_ROW, "trade_id": "T003"},
            ],
        )

        with pytest.raises(TradeBookValidationError) as exc:
            load(target)

        assert {e.trade_id for e in exc.value.report.errors} == {"T001", "T002"}

    def test_a_duplicate_is_reported_even_when_the_earlier_row_also_failed(
        self, tmp_path: Path
    ) -> None:
        """Both problems surface in one pass, so the file is fixable in one edit."""
        target = write_csv(
            tmp_path / "both.csv",
            [{**VALID_ROW, "volume_mw": "-5"}, VALID_ROW],
        )

        with pytest.raises(TradeBookValidationError) as exc:
            load(target)

        assert {e.field for e in exc.value.report.errors} == {"volume_mw", "trade_id"}

    def test_three_occurrences_report_two_duplicates(self, tmp_path: Path) -> None:
        target = write_csv(tmp_path / "triple.csv", [VALID_ROW, VALID_ROW, VALID_ROW])

        with pytest.raises(TradeBookValidationError) as exc:
            load(target)

        errors = exc.value.report.errors
        assert [e.row_number for e in errors] == [3, 4]
        assert all("already used on line 2" in e.reason for e in errors)


class TestErrorAggregation:
    def test_all_problems_are_collected_before_failing(self, tmp_path: Path) -> None:
        """S12: the run fails after collecting and reporting every validation error, so a
        user fixes the whole file in one edit rather than once per rerun."""
        target = write_csv(
            tmp_path / "many.csv",
            [
                {**VALID_ROW, "trade_id": "T001", "volume_mw": "-5"},
                {**VALID_ROW, "trade_id": "T002", "area": ""},
                {**VALID_ROW, "trade_id": "T003", "buy_sell": "Short"},
                {**VALID_ROW, "trade_id": "T004", "start_date": "2026-12-01"},
            ],
        )

        with pytest.raises(TradeBookValidationError) as exc:
            load(target)

        report = exc.value.report
        assert report.rows_read == 4
        assert report.rows_rejected == 4
        assert {e.field for e in report.errors} == {
            "volume_mw",
            "area",
            "buy_sell",
            "end_date",
        }

    def test_several_problems_in_one_row_are_all_reported(self, tmp_path: Path) -> None:
        target = write_csv(
            tmp_path / "bad_row.csv",
            [{**VALID_ROW, "volume_mw": "0", "price_jpy_kwh": "-1", "load_profile": "Peak"}],
        )

        with pytest.raises(TradeBookValidationError) as exc:
            load(target)

        report = exc.value.report
        assert report.rows_read == 1
        assert report.rows_rejected == 1
        assert len(report.errors) == 3

    def test_valid_rows_do_not_rescue_a_file_with_one_bad_row(self, tmp_path: Path) -> None:
        """A partial book would look like a complete position and could mislead a hedge."""
        target = write_csv(
            tmp_path / "mixed.csv",
            [VALID_ROW, {**VALID_ROW, "trade_id": "T002", "volume_mw": "-1"}],
        )

        with pytest.raises(TradeBookValidationError):
            load(target)

    def test_error_identifies_the_file_line_number(self, tmp_path: Path) -> None:
        """AC-14: row numbers match what an editor shows, header counted as line 1."""
        target = write_csv(
            tmp_path / "lines.csv",
            [
                VALID_ROW,
                {**VALID_ROW, "trade_id": "T002"},
                {**VALID_ROW, "trade_id": "T003", "volume_mw": "-1"},
            ],
        )

        with pytest.raises(TradeBookValidationError) as exc:
            load(target)

        error = exc.value.report.errors[0]
        assert error.row_number == 4
        assert error.trade_id == "T003"

    def test_a_row_is_attributed_to_its_trade_id_even_when_other_fields_fail(
        self, tmp_path: Path
    ) -> None:
        target = write_csv(tmp_path / "attr.csv", [{**VALID_ROW, "area": "", "volume_mw": "-1"}])

        with pytest.raises(TradeBookValidationError) as exc:
            load(target)

        assert {e.trade_id for e in exc.value.report.errors} == {"T001"}

    def test_the_message_summarises_and_names_the_source(self, tmp_path: Path) -> None:
        target = write_csv(tmp_path / "msg.csv", [{**VALID_ROW, "volume_mw": "-1"}])

        with pytest.raises(TradeBookValidationError) as exc:
            load(target)

        assert "msg.csv" in str(exc.value)
        assert "1 problem(s) in 1 of 1 row(s)" in str(exc.value)
        assert not exc.value.report.ok


class TestRetainedMetadata:
    def test_descriptive_fields_are_retained_without_being_parsed(self) -> None:
        """S4.3 and AC-16: product is metadata, never a source of delivery dates."""
        book = load(DEFAULT_TRADES_CSV)
        t005 = next(t for t in book if t.trade_id == "T005")

        assert t005.product == "Weekend 10-11 Oct-26 Base"
        assert t005.counterparty == "Minato Hedge Co"
        assert t005.price_jpy_kwh == Decimal("12.40")
        assert t005.interval.start.isoformat() == "2026-10-10"
        assert t005.interval.end.isoformat() == "2026-10-12"

    def test_a_misleading_product_name_does_not_change_the_interval(
        self, tmp_path: Path
    ) -> None:
        target = write_csv(tmp_path / "mislabelled.csv", [{**VALID_ROW, "product": "Cal-30 Peak"}])

        trade = load(target).trades[0]

        assert trade.product == "Cal-30 Peak"
        assert trade.profile.name == "Base", "load_profile is the only source of the shape"
        assert trade.interval.start.isoformat() == "2026-10-01"
