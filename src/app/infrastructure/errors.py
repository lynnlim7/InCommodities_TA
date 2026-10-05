"""Boundary failures: what went wrong with the input, in terms a user can act on.

requirements.md S12 asks the program to fail clearly, and AC-14 states what "clearly"
means: the row or trade, the field, the offending value, and the reason. Those four facts
are the shape of ``RowError``, so a message physically cannot be raised without them.

Two failure kinds are distinguished because they need different responses and different
exit codes: the source itself is unusable (missing file, wrong headers), or the source is
readable but its contents are invalid.
"""

from __future__ import annotations

from dataclasses import dataclass


class InputError(Exception):
    """Base class for a failure at the input boundary."""


class TradeSourceError(InputError):
    """The source could not be read at all: missing file, unreadable, wrong headers.

    Distinct from invalid contents because no row-level detail exists to report, and
    because the operator's fix is different -- point at another file, rather than correct
    a value inside this one.
    """


@dataclass(frozen=True, slots=True)
class RowError:
    """One reason one row was rejected.

    Every field here exists because AC-14 names it. ``row_number`` is the line number in
    the source file, counting the header as line 1, so it matches what an editor shows.
    """

    row_number: int | None
    trade_id: str | None
    field: str
    value: str
    reason: str

    def __str__(self) -> str:
        location = f"line {self.row_number}" if self.row_number is not None else "unknown line"
        if self.trade_id:
            location += f" (trade {self.trade_id})"
        return f"{location}: {self.field}={self.value} -- {self.reason}"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Every problem found in one pass over the source.

    Collected rather than raised on first sight so that a user fixes the whole file in one
    edit instead of rerunning once per bad row.
    """

    errors: tuple[RowError, ...]
    rows_read: int

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def rows_rejected(self) -> int:
        """Distinct rows with at least one problem; a row can fail several ways at once."""
        return len({e.row_number for e in self.errors})

    def summary(self) -> str:
        return (
            f"{len(self.errors)} problem(s) in {self.rows_rejected} of "
            f"{self.rows_read} row(s)"
        )

    def __str__(self) -> str:
        return "\n".join([self.summary(), *(f"  {e}" for e in self.errors)])


class TradeBookValidationError(InputError):
    """The source was readable but contained invalid records.

    The run is failed rather than continued with the valid subset (S12). A partial book
    still looks like a complete position, and a position that is quietly missing trades
    can produce a plausible but wrong hedge. Quarantining rows with a prominent
    incomplete-book warning is a reasonable future policy, but it must be an explicit
    choice rather than the silent default.
    """

    def __init__(self, report: ValidationReport, source: str) -> None:
        self.report = report
        self.source = source
        super().__init__(f"{source}: {report.summary()}")
