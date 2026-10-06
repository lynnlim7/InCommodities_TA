"""The row error an operator actually reads.

Every quarantined trade is listed on the dashboard with this message, so it
must name the line, the trade, the field, the value and the reason.
"""

import pytest

from app.infrastructure.errors import RowError

pytestmark = pytest.mark.unit


def test_a_row_error_names_the_line_trade_field_value_and_reason():
    error = RowError(
        row_number=2,
        trade_id="T001",
        field="volume_mw",
        value="-5",
        reason="Input should be greater than 0",
    )

    assert str(error) == (
        "line 2 (trade T001): volume_mw=-5 - Input should be greater than 0"
    )


def test_a_row_error_without_a_trade_id_still_names_the_line():
    error = RowError(row_number=7, field="trade_id", value="", reason="Required")

    assert str(error) == "line 7: trade_id= - Required"
