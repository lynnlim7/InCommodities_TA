"""Reading the trade book from a CSV file.

Responsibilities are kept narrow on purpose (requirements.md S14.1, S14.2): read rows,
turn each into a validated ``Trade``, and report what could not be converted. No position
arithmetic and no formatting happen here.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.core import DomainError, Trade, TradeBook
from app.infrastructure.errors import (
    RowError,
    TradeBookValidationError,
    TradeSourceError,
    ValidationReport,
)
from app.infrastructure.raw import CSV_HEADERS, RawTradeRow

DEFAULT_TRADES_CSV = Path(__file__).resolve().parent.parent / "data" / "trades.csv"
"""The supplied book, shipped with the package so a fresh checkout runs with no setup."""

_EXTRA_FIELDS_KEY = "__extra__"
_HEADER_LINES = 1
"""Row numbers are reported as file line numbers, so the header counts as line 1."""


@dataclass(frozen=True, slots=True)
class CsvTradeRepository:
    """Loads trades from a CSV file with the columns described in S4.1."""

    path: Path

    @property
    def source(self) -> str:
        return str(self.path)

    def load(self) -> TradeBook:
        """Read, validate, and return the whole book, or fail with every problem found."""
        trades: list[Trade] = []
        errors: list[RowError] = []
        identities: list[tuple[int, str]] = []
        rows_read = 0

        for line_number, row in self._rows():
            rows_read += 1
            trade_id = (row.get("trade_id") or "").strip() or None
            if trade_id is not None:
                identities.append((line_number, trade_id))
            errors.extend(_convert(row, line_number, trade_id, trades))

        errors.extend(_duplicate_id_errors(identities))

        if errors:
            report = ValidationReport(errors=tuple(errors), rows_read=rows_read)
            raise TradeBookValidationError(report, self.source)

        return TradeBook(tuple(trades))

    def _rows(self) -> list[tuple[int, dict[str, str]]]:
        """Read raw rows, failing on anything that makes the file itself unusable."""
        try:
            # utf-8-sig tolerates the byte-order mark that spreadsheet exports often add,
            # which would otherwise corrupt the first header name.
            with self.path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(
                    handle, restkey=_EXTRA_FIELDS_KEY, restval=""
                )
                _check_headers(reader.fieldnames, self.source)
                return [(reader.line_num, dict(row)) for row in reader]
        except FileNotFoundError:
            raise TradeSourceError(f"input file not found: {self.source}") from None
        except IsADirectoryError:
            raise TradeSourceError(
                f"input path is a directory, not a file: {self.source}"
            ) from None
        except OSError as exc:
            raise TradeSourceError(f"could not read {self.source}: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise TradeSourceError(
                f"{self.source} is not valid UTF-8 text at byte {exc.start}"
            ) from exc


def _check_headers(fieldnames: Sequence[str] | None, source: str) -> None:
    """Validate the header row before parsing any data (S12).

    Checked up front so a renamed column produces one clear message instead of the same
    error repeated for every row in the file.
    """
    if not fieldnames:
        raise TradeSourceError(f"{source} is empty: no header row found")

    seen = [name.strip() for name in fieldnames]
    duplicates = sorted({name for name in seen if seen.count(name) > 1})
    if duplicates:
        raise TradeSourceError(f"{source} has duplicate columns: {', '.join(duplicates)}")

    missing = [name for name in CSV_HEADERS if name not in seen]
    unexpected = [name for name in seen if name not in CSV_HEADERS]
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing columns: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected columns: {', '.join(unexpected)}")
        raise TradeSourceError(
            f"{source} has the wrong columns ({'; '.join(details)}). "
            f"Expected exactly: {', '.join(CSV_HEADERS)}"
        )


def _convert(
    row: dict[str, str], line_number: int, trade_id: str | None, into: list[Trade]
) -> list[RowError]:
    """Validate one row, appending the trade on success and returning errors on failure."""
    extra = row.pop(_EXTRA_FIELDS_KEY, None)
    if extra:
        return [
            RowError(
                row_number=line_number,
                trade_id=trade_id,
                field="(row)",
                value=_display(extra),
                reason=f"row has more fields than the {len(CSV_HEADERS)} declared columns",
            )
        ]

    try:
        # model_validate, not the constructor: these are untrusted strings, and this is
        # the Pydantic entry point that coerces and validates rather than assuming the
        # values already match the declared types.
        into.append(RawTradeRow.model_validate(row).to_trade())
    except ValidationError as exc:
        return _row_errors(exc, line_number, trade_id)
    except DomainError as exc:
        # A domain invariant that field validation did not already cover. Reaching this
        # means the boundary model and the domain disagree, so it is reported rather
        # than allowed to escape as an unhandled exception.
        return [
            RowError(
                row_number=line_number,
                trade_id=trade_id,
                field="(row)",
                value="",
                reason=str(exc),
            )
        ]
    return []


def _row_errors(exc: ValidationError, line_number: int, trade_id: str | None) -> list[RowError]:
    """Translate Pydantic's report into the four facts AC-14 requires."""
    return [
        RowError(
            row_number=line_number,
            trade_id=trade_id,
            field=".".join(str(part) for part in error["loc"]) or "(row)",
            value=_display(error.get("input")),
            reason=_reason(str(error["msg"])),
        )
        for error in exc.errors()
    ]


def _duplicate_id_errors(identities: list[tuple[int, str]]) -> list[RowError]:
    """Report every row whose trade_id repeats one seen on an earlier line.

    Driven by the raw trade_id column rather than by successfully converted trades, so a
    duplicate is still reported when the earlier row also failed for another reason --
    otherwise a user would fix the other problem, rerun, and only then discover the
    duplicate.

    Found here rather than left to ``TradeBook`` so the message can name the lines.
    ``TradeBook`` still enforces the rule for any other source of trades (AC-15).
    """
    first_seen: dict[str, int] = {}
    errors: list[RowError] = []
    for line_number, trade_id in identities:
        earlier = first_seen.setdefault(trade_id, line_number)
        if earlier == line_number:
            continue
        errors.append(
            RowError(
                row_number=line_number,
                trade_id=trade_id,
                field="trade_id",
                value=_display(trade_id),
                reason=(
                    f"duplicate trade_id, already used on line {earlier}; ids must be "
                    f"unique, and rows are rejected rather than deduplicated because "
                    f"dropping one could halve a real position"
                ),
            )
        )
    return errors


def _reason(message: str) -> str:
    """Strip Pydantic's wrapper so the domain's own wording leads the message."""
    prefix = "Value error, "
    return message[len(prefix) :] if message.startswith(prefix) else message


def _display(value: object) -> str:
    """Render an offending value for a message, keeping empty and blank input visible."""
    if value is None:
        return "(missing)"
    if isinstance(value, str) and not value.strip():
        return repr(value)
    return str(value)
