"""
Load and validate trades from CSV file.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.core.models import DeliveryPeriod, Trade, TradeBook
from app.infrastructure.errors import RowError, TradeBookValidationError, TradeSourceError
from app.infrastructure.schemas import CSV_HEADERS, CsvTradeRow

DEFAULT_TRADES_CSV = (
    Path(__file__).resolve().parent.parent / "data" / "trades.csv"
)

@dataclass(frozen=True, slots=True)
class CsvTradeRepository:
    """Loads and validate trade rows from CSV file."""

    path: Path

    def load(self) -> TradeBook:
        rows = self._load_rows()

        return TradeBook(
            trades=tuple(
                _to_trade(row)
                for row in rows
            )
        )

    def _load_rows(self) -> list[CsvTradeRow]:
        """Return validated trade rows or raise all validation errors."""
        rows: list[CsvTradeRow] = []
        errors: list[RowError] = []
        seen_ids: dict[str, int] = {} # prevent dupes
        rows_read = 0

        try:
            with self.path.open(newline="", encoding="utf-8-sig") as file: 
                reader = csv.DictReader(file)

                _validate_headers(reader.fieldnames, self.path)

                for line_number, row in enumerate(reader, start=2):
                    rows_read += 1

                    trade_id = (
                        (row.get("trade_id") or "").strip()
                    )

                    # check for unique trade ids 
                    if trade_id: 
                        first_line = seen_ids.get(trade_id)

                        if first_line is not None: 
                            errors.append(
                                RowError(
                                    row_number=line_number,
                                    trade_id=trade_id,
                                    field="trade_id",
                                    value=trade_id,
                                    reason=(
                                        "Duplicate trade_id: "
                                        f"first used on line {first_line}"
                                    ),
                                )
                            )
                        else: 
                            seen_ids[trade_id] = line_number

                    try: 
                        row_model = CsvTradeRow.model_validate(row)
                        rows.append(row_model)

                    except ValidationError as exc:
                        errors.extend(
                            _validation_errors(
                                exc, 
                                line_number,
                                trade_id
                            )
                        )
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

        if errors:
            raise TradeBookValidationError(
                errors=errors,
                rows_read=rows_read,
            )

        return rows



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
        

      