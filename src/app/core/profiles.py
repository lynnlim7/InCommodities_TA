"""Load profiles: how many hours of an interval a trade actually delivers in.

This is the project's main extension point. A profile answers exactly one question --
"how many hours of this interval do you cover?" -- and knows nothing about direction,
netting, areas, or reporting windows. Adding Peak, or any other shape, therefore means
adding one class and registering it; the netting and reporting arithmetic is untouched
(requirements.md S3.2, AC-19).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.core.errors import UnsupportedLoadProfileError
from app.core.interval import HOURS_PER_DAY, DateInterval


@runtime_checkable
class LoadProfile(Protocol):
    """A rule for the hours within an interval that a trade delivers in."""

    name: str

    def covered_hours(self, interval: DateInterval) -> Decimal:
        """Hours inside ``interval`` covered by this profile.

        The interval is already clipped to the overlap of delivery and reporting periods
        by the caller, so an implementation never needs to reason about either.
        """
        ...


class BaseProfile:
    """Baseload: delivers in every hour of every delivery day (requirements.md S5.1).

    Covered hours are counted as whole days multiplied by 24 rather than by walking each
    hour. That is an optimisation of the hour count, not a different model -- the result
    is identical to summing 24 one-hour slots (S6.2).
    """

    name = "Base"

    def covered_hours(self, interval: DateInterval) -> Decimal:
        return Decimal(interval.days * HOURS_PER_DAY)


_REGISTRY: dict[str, LoadProfile] = {}


def register_profile(profile: LoadProfile) -> None:
    """Make a profile available to parsing. Re-registering a name replaces it."""
    _REGISTRY[profile.name.casefold()] = profile


def parse_profile(raw: str) -> LoadProfile:
    """Resolve an external load_profile string to its covered-hour rule.

    An unregistered profile is rejected rather than defaulted to Base: silently treating
    an unknown shape as baseload would overstate delivered volume (S5.3, S12).
    """
    try:
        return _REGISTRY[raw.strip().casefold()]
    except KeyError:
        supported = ", ".join(sorted(p.name for p in _REGISTRY.values()))
        raise UnsupportedLoadProfileError(
            f"unsupported load_profile {raw!r}; registered profiles are: {supported}"
        ) from None


def registered_profiles() -> tuple[str, ...]:
    """Names of every registered profile, for diagnostics and tests."""
    return tuple(sorted(p.name for p in _REGISTRY.values()))


BASE = BaseProfile()
register_profile(BASE)
