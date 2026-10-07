"""
Build domain load profiles from validated configuration.
"""

import calendar

from app.config.schema import (
    ContinuousProfileConfig,
    HourlyWindowProfileConfig,
    LoadProfilesConfig,
)
from app.core.profiles import (
    ContinuousProfile,
    HourlyWindowProfile,
    LoadProfile,
    ProfileRegistry,
)

WEEKDAY_INDEX = {
    name: index
    for index, name in enumerate(calendar.day_name)
}


def build_profile_registry(
    config: LoadProfilesConfig,
) -> ProfileRegistry:
    """Build load-profile behaviours from validated configuration."""

    profiles: dict[str, LoadProfile] = {}

    for name, profile_config in config.load_profiles.items():

        if isinstance(
            profile_config,
            ContinuousProfileConfig,
        ):
            profiles[name] = ContinuousProfile()

        elif isinstance(
            profile_config,
            HourlyWindowProfileConfig,
        ):
            profiles[name] = HourlyWindowProfile(
                start_hour=profile_config.start_hour,
                end_hour=profile_config.end_hour,
                weekdays=frozenset(
                    WEEKDAY_INDEX[weekday]
                    for weekday in profile_config.weekdays
                ),
            )

    return ProfileRegistry(
        profiles=profiles,
    )