"""
Load profiles behaviour for position calculations.
"""

from __future__ import annotations

from collections.abc import ItemsView
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Protocol

from app.core.errors import (
    InvalidProfileError,
    UnsupportedProfileError,
)
from app.core.models import DeliveryPeriod


class LoadProfile(Protocol):
    """How many hours a load profile actually delivers inside an interval."""

    def delivery_hours(
            self,
            period: DeliveryPeriod,
    ) -> Decimal:
        ...

@dataclass(frozen=True, slots=True)
class ContinuousProfile:
    """Profile delivering continuously throughout its period."""

    def delivery_hours(
        self,
        period: DeliveryPeriod,
    ) -> Decimal:
        """Return delivery hours within the period."""

        days = (period.end - period.start).days

        return Decimal(days * 24)


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