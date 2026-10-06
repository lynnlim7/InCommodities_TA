"""The validation report an operator actually reads.

The report is the whole product of the one-pass validation policy: if it is
unreadable, collecting every problem in the file buys nothing. Only the
summary line is pinned here -- the per-row detail is already covered through
the repository, which is where the row numbers and field names come from.
"""

import pytest

from app.infrastructure.errors import RowError, TradeBookValidationError

pytestmark = pytest.mark.unit


def row_error(row_number: int) -> RowError:
    return RowError(
        row_number=row_number,
        trade_id="T001",
        field="volume_mw",
        value="-5",
        reason="Input should be greater than 0",
    )


def test_a_single_problem_in_a_single_row_reads_in_the_singular():
    report = TradeBookValidationError(errors=[row_error(2)], rows_read=1)

    assert str(report).startswith("1 validation error in 1 row read")


def test_multiple_problems_read_in_the_plural():
    report = TradeBookValidationError(
        errors=[row_error(2), row_error(3)],
        rows_read=3,
    )

    assert str(report).startswith("2 validation errors in 3 rows read")


def test_every_collected_problem_appears_in_the_report():
    report = TradeBookValidationError(
        errors=[row_error(2), row_error(3)],
        rows_read=3,
    )

    assert "line 2 (trade T001): volume_mw=-5 - Input should be greater than 0" in str(report)
    assert "line 3 (trade T001): volume_mw=-5 - Input should be greater than 0" in str(report)
