"""Presentation formatting rules.

Only the deterministic rules a trader reads off the screen are tested: the
delivery labels, the signed MW and MWh formats, and the long/short/flat
classification. Streamlit itself is not tested, and no calculation is
repeated here.
"""

from decimal import Decimal

import pytest

from app.dashboard.formatting import (
    format_daily_label,
    format_energy,
    format_monthly_label,
    format_position,
    format_weekly_label,
    position_state,
)
from tests.builders import delivery

pytestmark = pytest.mark.unit


def test_a_daily_period_is_labelled_with_its_single_delivery_day():
    assert format_daily_label(delivery("2026-10-01", "2026-10-02")) == "01 Oct 2026"


def test_a_weekly_label_shows_the_last_delivered_day_not_the_exclusive_boundary():
    """[01 Oct, 05 Oct) delivers through 04 Oct, so that is what is shown.

    Printing "01 Oct - 05 Oct" would put the internal exclusive boundary on
    the screen and overstate the delivery by a day.
    """
    assert format_weekly_label(delivery("2026-10-01", "2026-10-05")) == "01 Oct - 04 Oct 2026"
    assert format_weekly_label(delivery("2026-10-05", "2026-10-12")) == "05 Oct - 11 Oct 2026"


def test_a_weekly_label_spanning_a_year_end_shows_both_years():
    assert (
        format_weekly_label(delivery("2026-12-28", "2027-01-04"))
        == "28 Dec 2026 - 03 Jan 2027"
    )


def test_a_single_day_weekly_bucket_collapses_to_one_date():
    """A Sunday as-of date leaves one day in the current week."""
    assert format_weekly_label(delivery("2026-10-04", "2026-10-05")) == "04 Oct 2026"


def test_a_monthly_label_names_the_calendar_month_even_when_clipped():
    assert format_monthly_label(delivery("2026-10-01", "2026-11-01")) == "Oct 2026"
    assert format_monthly_label(delivery("2026-10-15", "2026-11-01")) == "Oct 2026"
    assert format_monthly_label(delivery("2027-01-01", "2027-02-01")) == "Jan 2027"


@pytest.mark.parametrize(
    ("net_position_mw", "expected"),
    [
        ("10", "+10.00"),
        ("-5", "-5.00"),
        ("0", "0.00"),
        ("31.741935483870967741935483871", "+31.74"),
        ("-0.004", "0.00"),  # rounds away; a "-0.00" minus sign would mislead
        ("-0.005", "-0.01"),  # half-up rounds away from zero
        ("1234.5", "+1,234.50"),
    ],
)
def test_positions_are_formatted_with_a_consistent_signed_two_place_value(
    net_position_mw, expected
):
    assert format_position(Decimal(net_position_mw)) == expected


@pytest.mark.parametrize(
    ("net_position_mwh", "expected"),
    [
        ("7440", "+7,440"),
        ("-7440", "-7,440"),
        ("0", "0"),
        ("3360.5", "+3,361"),  # half-up, and MWh is read at whole units
        ("-0.4", "0"),  # rounds away; a "-0" minus sign would mislead
        ("-0.5", "-1"),  # half-up rounds away from zero
    ],
)
def test_energy_is_formatted_as_a_signed_whole_mwh_total(
    net_position_mwh, expected
):
    """Energy runs into the thousands, where decimals are noise not detail.

    MW is a rate read at two places; MWh is a cumulative total and is
    thousands of times larger, so showing it at the same precision would add
    digits a trader never acts on. The signed presentation is shared, so both
    columns of a row still read as one position.
    """
    assert format_energy(Decimal(net_position_mwh)) == expected


@pytest.mark.parametrize(
    ("net_position_mw", "expected"),
    [
        ("10", "long"),
        ("-5", "short"),
        ("0", "flat"),
        ("0.001", "long"),  # direction is read before rounding
        ("-0.001", "short"),
    ],
)
def test_direction_is_classified_from_the_unrounded_position(net_position_mw, expected):
    """A position too small to print at two places is still long or short.

    Rounding first would report a real exposure as flat, so the row colour is
    driven by the calculated value and only the printed number is rounded.
    """
    assert position_state(Decimal(net_position_mw)) == expected
