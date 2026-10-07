"""
Load and validate trades from CSV file.

A broken file fails the run. 
A bad row is quarantined with every reason it failed, and the rest of the book is still loaded.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from app.core.models import (
    DeliveryPeriod,
    ExcludedTrade,
    ReferenceData,
    Trade,
    TradeBook,
)
from app.infrastructure.errors import RowError, TradeSourceError
from app.infrastructure.schemas import CSV_HEADERS, CsvTradeRow

DEFAULT_TRADES_CSV = (
    Path(__file__).resolve().parent.parent / "data" / "trades.csv"
)

RawRow = dict[str, str]


@dataclass(frozen=True, slots=True)
class QuarantinedRow:
    """A row left out of the book, with every reason it failed."""

    row_number: int
    errors: tuple[RowError, ...]
    excluded: ExcludedTrade


@dataclass(frozen=True, slots=True)
class LoadResult:
    """The trades that load cleanly, and the rows quarantined."""

    trade_book: TradeBook
    quarantined: tuple[QuarantinedRow, ...]
    rows_read: int

    @property
    def excluded_trades(self) -> tuple[ExcludedTrade, ...]:
        return tuple(row.excluded for row in self.quarantined)


@dataclass(frozen=True, slots=True)
class CsvTradeRepository:
    """Loads and validate trade rows from CSV file."""

    path: Path
    reference: ReferenceData

    def load(self) -> LoadResult:
        rows = self._read_rows()
        duplicates = _duplicate_trade_ids(rows)

        trades: list[Trade] = []
        quarantined: list[QuarantinedRow] = []

        for line_number, row in rows:
            trade_id = _trade_id(row)
            row_model, errors = _validate_row(
                row, line_number, trade_id, self.reference, duplicates
            )

            if row_model is None or errors:
                quarantined.append(
                    QuarantinedRow(
                        row_number=line_number,
                        errors=tuple(errors),
                        excluded=_readable_part(row, trade_id, self.reference),
                    )
                )
            else:
                trades.append(_to_trade(row_model))

        return LoadResult(
            trade_book=TradeBook(trades=tuple(trades)),
            quarantined=tuple(quarantined),
            rows_read=len(rows),
        )

    def _read_rows(self) -> list[tuple[int, RawRow]]:
        """Return every data row with its CSV line number, or fail on a broken file."""
        try:
            with self.path.open(newline="", encoding="utf-8-sig") as file:
                reader = csv.DictReader(file)

                _validate_headers(reader.fieldnames, self.path)

                return list(enumerate(reader, start=2))

        except FileNotFoundError:
            raise TradeSourceError(
                f"Input file not found: {self.path}"
            ) from None

        except IsADirectoryError:
            raise TradeSourceError(
                f"Input path is a directory: {self.path}"
            ) from None

        except UnicodeDecodeError:
            raise TradeSourceError(
                f"Input file is not valid UTF-8: {self.path}"
            ) from None

        except OSError as exc:
            raise TradeSourceError(
                f"Could not read {self.path}: {exc}"
            ) from exc


def _validate_row(
    row: RawRow,
    line_number: int,
    trade_id: str | None,
    reference: ReferenceData,
    duplicates: dict[str, list[int]],
) -> tuple[CsvTradeRow | None, list[RowError]]:
    """Parse one row and return every reason it cannot be counted."""

    if None in row:
        return None, [
            RowError(
                row_number=line_number,
                trade_id=trade_id,
                field="(row)",
                value="",
                reason="More values than columns; the row's values may be shifted",
            )
        ]

    errors: list[RowError] = []

    if trade_id in duplicates:
        lines = ", ".join(str(line) for line in duplicates[trade_id])
        errors.append(
            RowError(
                row_number=line_number,
                trade_id=trade_id,
                field="trade_id",
                value=trade_id,
                reason=f"Duplicate trade_id: used on lines {lines}",
            )
        )

    try:
        row_model = CsvTradeRow.model_validate(row)
    except ValidationError as exc:
        return None, errors + _validation_errors(exc, line_number, trade_id)

    return row_model, errors + _reference_errors(row_model, line_number, reference)


def _reference_errors(
    row: CsvTradeRow,
    line_number: int,
    reference: ReferenceData,
) -> list[RowError]:
    """Area, trade type and load profile must each be configured."""

    checks = (
        ("area", row.area, reference.areas),
        ("trade_type", row.trade_type, reference.trade_types),
        ("load_profile", row.load_profile, reference.load_profiles),
    )

    return [
        RowError(
            row_number=line_number,
            trade_id=row.trade_id,
            field=name,
            value=value,
            reason=f"Not configured; expected one of {sorted(allowed)}",
        )
        for name, value, allowed in checks
        if value not in allowed
    ]


def _readable_part(
    row: RawRow,
    trade_id: str | None,
    reference: ReferenceData,
) -> ExcludedTrade:
    """Keep the area and delivery of a quarantined row if they can be read."""

    area = (row.get("area") or "").strip()

    return ExcludedTrade(
        trade_id=trade_id,
        area=area if area in reference.areas else None,
        delivery=_readable_delivery(row),
    )


def _readable_delivery(row: RawRow) -> DeliveryPeriod | None:
    try:
        start = date.fromisoformat((row.get("start_date") or "").strip())
        end = date.fromisoformat((row.get("end_date") or "").strip())
    except ValueError:
        return None

    if start >= end:
        return None

    return DeliveryPeriod(start=start, end=end)


def _duplicate_trade_ids(
    rows: list[tuple[int, RawRow]],
) -> dict[str, list[int]]:
    """Trade ids on more than one line. Every copy is quarantined: neither is guessed at."""

    lines_by_id: dict[str, list[int]] = defaultdict(list)

    for line_number, row in rows:
        trade_id = _trade_id(row)

        if trade_id is not None:
            lines_by_id[trade_id].append(line_number)

    return {
        trade_id: lines
        for trade_id, lines in lines_by_id.items()
        if len(lines) > 1
    }


def _trade_id(row: RawRow) -> str | None:
    return (row.get("trade_id") or "").strip() or None


def _to_trade(
    row:CsvTradeRow,
) -> Trade:
    """Convert validated CSV row into domain trade."""
    return Trade(
        trade_id=row.trade_id,
        area=row.area,
        trade_type=row.trade_type,
        buy_sell=row.buy_sell,
        load_profile=row.load_profile,
        delivery=DeliveryPeriod(
            start=row.start_date,
            end=row.end_date,
        ),
        volume_mw=row.volume_mw,
        product=row.product,
    )

def _validate_headers(
        fieldnames: Sequence[str] | None,
        source: Path,
) -> None:
    """Validate CSV columns before processing rows."""

    if not fieldnames:
        raise TradeSourceError(
            f"{source} has no header row"
        )

    actual = [field.strip() for field in fieldnames]

    if len(actual) != len(set(actual)):
        raise TradeSourceError(
            f"{source} has duplicate columns"
        )

    missing = set(CSV_HEADERS) - set(actual)
    unexpected = set(actual) - set(CSV_HEADERS)

    if missing or unexpected:
        raise TradeSourceError(
            f"{source} has invalid columns. "
            f"Missing: {sorted(missing)}. "
            f"Unexpected: {sorted(unexpected)}"
        )

def _validation_errors(
        exc: ValidationError,
        line_number: int,
        trade_id: str | None,
) -> list[RowError]:
    """Convert Pydantic validation errors into CSV row errors."""

    return [
        RowError(
            row_number=line_number,
            trade_id=trade_id,
            field=".".join(str(part) for part in error["loc"]) or "(row)",
            value=str(error.get("input", "")),
            reason=str(error["msg"])
        )
        for error in exc.errors()
    ]
