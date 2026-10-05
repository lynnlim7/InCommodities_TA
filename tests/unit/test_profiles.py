"""Load profile covered hours and the profile registry (AC-05, AC-19)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core import (
    BASE,
    DateInterval,
    LoadProfile,
    UnsupportedLoadProfileError,
    parse_profile,
    register_profile,
    registered_profiles,
)

pytestmark = pytest.mark.unit


def test_base_covers_every_hour_of_one_day() -> None:
    """AC-05: a Base trade covering one complete day covers all 24 hours."""
    one_day = DateInterval(date(2026, 10, 1), date(2026, 10, 2))

    assert BASE.covered_hours(one_day) == Decimal(24)


def test_base_covers_every_hour_of_a_month() -> None:
    october = DateInterval(date(2026, 10, 1), date(2026, 11, 1))

    assert BASE.covered_hours(october) == Decimal(744)


def test_base_covered_hours_match_wall_clock_hours() -> None:
    """Baseload delivers continuously, so covered hours equal the interval's own hours."""
    interval = DateInterval(date(2026, 10, 1), date(2027, 4, 1))

    assert BASE.covered_hours(interval) == interval.hours


def test_base_is_registered_under_its_csv_spelling() -> None:
    assert parse_profile("Base") is BASE
    assert "Base" in registered_profiles()


@pytest.mark.parametrize("raw", ["base", "BASE", " Base "])
def test_parse_accepts_case_and_whitespace_variants(raw: str) -> None:
    assert parse_profile(raw) is BASE


def test_unknown_profile_is_rejected_rather_than_defaulted_to_base() -> None:
    with pytest.raises(UnsupportedLoadProfileError) as exc:
        parse_profile("Peak")

    message = str(exc.value)
    assert "'Peak'" in message
    assert "Base" in message, "the message must list what is supported (AC-14)"


def test_a_profile_defined_outside_the_package_plugs_in_unchanged(
    clean_profile_registry: None,
) -> None:
    """AC-19: supporting a new shape must not require editing the domain.

    This profile is declared here, in the test module, and registered at runtime. It
    satisfies LoadProfile structurally -- there is no base class to inherit -- which is
    what proves the extension point is real rather than asserted.
    """

    class QuarterDayProfile:
        name = "QuarterDay"

        def covered_hours(self, interval: DateInterval) -> Decimal:
            return Decimal(interval.days * 6)

    profile = QuarterDayProfile()
    assert isinstance(profile, LoadProfile)

    register_profile(profile)

    assert parse_profile("quarterday") is profile
    two_days = DateInterval(date(2026, 10, 1), date(2026, 10, 3))
    assert profile.covered_hours(two_days) == Decimal(12)
