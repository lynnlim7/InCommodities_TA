"""
Load profiles behaviour for position calculations.
"""

from __future__ import annotations

from collections.abc import ItemsView
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from app.core.errors import (
    InvalidProfileError,
    UnsupportedProfileError,
)
from app.core.models import DeliveryPeriod

HOURS_PER_DAY = 24

ALL_HOURS = frozenset(range(HOURS_PER_DAY))
NO_HOURS: frozenset[int] = frozenset()


class LoadProfile(Protocol):
    """Which hours a load profile actually delivers."""

    def hours_on(
            self,
            day: date,
    ) -> frozenset[int]:
        ...

    def delivery_hours(
            self,
            period: DeliveryPeriod,
    ) -> Decimal:
        ...

@dataclass(frozen=True, slots=True)
class ContinuousProfile:
    """Profile delivering continuously throughout its period."""

    def hours_on(
        self,
        day: date,
    ) -> frozenset[int]:
        """Every hour of every day."""
        return ALL_HOURS

    def delivery_hours(
        self,
        period: DeliveryPeriod,
    ) -> Decimal:
        """Return delivery hours within the period."""

        days = (period.end - period.start).days

        return Decimal(days * HOURS_PER_DAY)


@dataclass(frozen=True, slots=True)
class HourlyWindowProfile:
    """Profile delivering during configured hours and weekdays."""

    start_hour: int
    end_hour: int
    weekdays: frozenset[int]

    def __post_init__(self) -> None:
        if not 0 <= self.start_hour < 24:
            raise InvalidProfileError(
                "start_hour must be between 0 and 23."
            )

        if not 1 <= self.end_hour <= 24:
            raise InvalidProfileError(
                "end_hour must be between 1 and 24."
            )

        if self.start_hour >= self.end_hour:
            raise InvalidProfileError(
                "start_hour must be before end_hour."
            )

        if not self.weekdays:
            raise InvalidProfileError(
                "hourly window profile requires at least one weekday."
            )

    def hours_on(
        self,
        day: date,
    ) -> frozenset[int]:
        """The configured window on a delivery weekday, nothing otherwise."""

        if day.weekday() not in self.weekdays:
            return NO_HOURS

        return frozenset(range(self.start_hour, self.end_hour))

    def delivery_hours(
        self,
        period: DeliveryPeriod,
    ) -> Decimal:
        """Return configured delivery hours within the period."""

        hours_per_day = self.end_hour - self.start_hour
        delivery_days = 0

        current = period.start

        while current < period.end:
            if current.weekday() in self.weekdays:
                delivery_days += 1

            current += timedelta(days=1)

        return Decimal(delivery_days * hours_per_day)


@dataclass(frozen=True, slots=True)
class ProfileRegistry:
    """Configured load profiles available to the position engine."""

    profiles: dict[str, LoadProfile]

    def get(
        self,
        name: str,
    ) -> LoadProfile:
        try:
            return self.profiles[name]
        except KeyError:
            raise UnsupportedProfileError(
                f"Unsupported load profile: {name}"
            ) from None

    def items(self) -> ItemsView[str, LoadProfile]:
        """Configured profiles by name, in configuration order."""
        return self.profiles.items()
