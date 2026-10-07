"""Configuration to domain translation.

Pydantic's own validation is not retested here. What is tested is the
application's own behaviour: that a validated YAML profile declaration turns
into the right domain profile with the right parameters, and that the shipped
configuration file does so too.

This is the seam that keeps "Base" and "Peak" out of the calculation engine.
If the translation is wrong the engine still runs and still reports a number,
just the wrong one -- so it is worth a test.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from app.config import loader
from app.config.loader import load_yaml
from app.config.profile_registry import build_profile_registry
from app.config.schema import LoadProfilesConfig
from app.core.errors import InvalidProfileError
from app.core.profiles import ContinuousProfile, HourlyWindowProfile
from tests.builders import delivery

pytestmark = pytest.mark.unit

# ``app.config`` has no __init__.py, so locate the shipped YAML via the
# loader module rather than the package.
SHIPPED_CONFIG = Path(loader.__file__).parent / "load_profiles.yaml"


def test_declared_profiles_become_the_matching_domain_behaviour():
    config = LoadProfilesConfig.model_validate(
        {
            "load_profiles": {
                "Base": {"type": "continuous"},
                "Peak": {
                    "type": "hourly_window",
                    "start_hour": 8,
                    "end_hour": 20,
                    "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                },
            }
        }
    )

    registry = build_profile_registry(config)

    assert registry.get("Base") == ContinuousProfile()
    assert registry.get("Peak") == HourlyWindowProfile(
        start_hour=8,
        end_hour=20,
        weekdays=frozenset({0, 1, 2, 3, 4}),
    )


def test_shipped_configuration_produces_the_intended_delivery_hours():
    """The file the application actually ships with is checked end to end.

    Asserting on delivery hours rather than on the registry's types is what
    makes this test worth having: it catches a weekday name mapped to the
    wrong index, which a type assertion would not.
    """
    registry = build_profile_registry(load_yaml(SHIPPED_CONFIG, LoadProfilesConfig))
    week = delivery("2026-10-05", "2026-10-12")  # one Monday-Sunday week

    assert registry.get("Base").delivery_hours(week) == Decimal("168")
    assert registry.get("Peak").delivery_hours(week) == Decimal("60")


def test_an_inverted_configured_window_is_rejected_by_the_domain():
    """Hours 20 to 8 satisfy the schema but not the domain.

    Each bound is individually in range, so Pydantic accepts the file; the
    rule that the window must be positive lives in the domain, and the
    translation step is where it is enforced.
    """
    config = LoadProfilesConfig.model_validate(
        {
            "load_profiles": {
                "Peak": {
                    "type": "hourly_window",
                    "start_hour": 20,
                    "end_hour": 8,
                    "weekdays": ["Monday"],
                }
            }
        }
    )

    with pytest.raises(InvalidProfileError):
        build_profile_registry(config)


def test_weekend_days_translate_to_the_correct_weekday_indices():
    """Saturday and Sunday map to 5 and 6, not to some other pair.

    The domain always supported any weekday set; the schema now admits the
    weekend too, so this is the first configuration that can reach indices 5
    and 6. The mapping comes from ``calendar.day_name`` ordering, which is
    silent when wrong -- an off-by-one would shift a whole profile onto the
    wrong days and still report a plausible number.
    """
    config = LoadProfilesConfig.model_validate(
        {
            "load_profiles": {
                "Weekend": {
                    "type": "hourly_window",
                    "start_hour": 8,
                    "end_hour": 20,
                    "weekdays": ["Saturday", "Sunday"],
                }
            }
        }
    )

    weekend = build_profile_registry(config).get("Weekend")

    assert weekend == HourlyWindowProfile(
        start_hour=8,
        end_hour=20,
        weekdays=frozenset({5, 6}),
    )
    # One Monday-Sunday week delivers only its two weekend days: 2 x 12.
    assert weekend.delivery_hours(delivery("2026-10-05", "2026-10-12")) == Decimal("24")
