"""Load-profile delivery hours.

A profile answers exactly one question -- how many hours does this profile
actually deliver inside this interval -- and that answer is the weight in the
time-weighted position, so it is business critical.

Profiles are constructed here with explicit parameters rather than read from
configuration: the calculation engine must never branch on the names "Base" or
"Peak", and these tests mirror that by never using them.
"""

from decimal import Decimal

import pytest

from app.core.errors import InvalidProfileError, UnsupportedProfileError
from app.core.profiles import ContinuousProfile, HourlyWindowProfile, ProfileRegistry
from tests.helpers import delivery

pytestmark = pytest.mark.unit

WEEKDAYS = frozenset({0, 1, 2, 3, 4})  # Monday-Friday


def test_continuous_profile_delivers_every_hour_of_every_day():
    """Seven calendar days of continuous delivery is 7 x 24 = 168 hours."""
    week = delivery("2026-10-05", "2026-10-12")

    assert ContinuousProfile().delivery_hours(week) == Decimal("168")


def test_hourly_window_profile_delivers_only_its_configured_window():
    """08:00-20:00 on Monday-Friday over one week is 5 x 12 = 60 hours."""
    week = delivery("2026-10-05", "2026-10-12")  # Monday to Sunday
    peak = HourlyWindowProfile(start_hour=8, end_hour=20, weekdays=WEEKDAYS)

    assert peak.delivery_hours(week) == Decimal("60")


def test_hourly_window_profile_delivers_nothing_over_a_weekend():
    """Saturday and Sunday are not configured delivery days, so Peak is zero.

    This is the case that makes a Peak position undefined rather than merely
    small, and the engine has to cope with it.
    """
    weekend = delivery("2026-10-10", "2026-10-12")  # Saturday and Sunday
    peak = HourlyWindowProfile(start_hour=8, end_hour=20, weekdays=WEEKDAYS)

    assert peak.delivery_hours(weekend) == Decimal("0")


def test_hourly_window_profile_rejects_an_inverted_window():
    """start_hour 20 to end_hour 8 would silently yield negative hours.

    Negative hours would flip the sign of a position, so the domain rejects
    the configuration instead of calculating with it. One representative
    invalid window is tested; the remaining bound checks are the same rule.
    """
    with pytest.raises(InvalidProfileError):
        HourlyWindowProfile(start_hour=20, end_hour=8, weekdays=WEEKDAYS)


def test_hourly_window_profile_requires_at_least_one_delivery_day():
    with pytest.raises(InvalidProfileError):
        HourlyWindowProfile(start_hour=8, end_hour=20, weekdays=frozenset())


def test_registry_rejects_a_load_profile_it_was_not_configured_with():
    """An unknown profile fails the run rather than being treated as Base.

    Defaulting would report a position for a product whose delivery shape is
    unknown, which is worse than reporting nothing.
    """
    registry = ProfileRegistry(profiles={"Base": ContinuousProfile()})

    with pytest.raises(UnsupportedProfileError):
        registry.get("Peak")
