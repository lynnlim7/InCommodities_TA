"""Reference data and configuration.

This module holds declarative reference data only: no I/O, no clock, no behaviour.
It is the one place a new delivery area becomes visible to the application, which is
what keeps areas a data dimension rather than a code branch (requirements.md AC-18).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass

# The nine Japanese delivery areas, north to south. This list controls *display order*
# only -- an area absent from it is still valid and still calculated, it simply sorts
# after the known areas. Restricting input to an authoritative list is an open question
# (requirements.md S18.5) and is deliberately not decided here.
AREA_DISPLAY_ORDER: tuple[str, ...] = (
    "Hokkaido",
    "Tohoku",
    "Tokyo",
    "Chubu",
    "Hokuriku",
    "Kansai",
    "Chugoku",
    "Shikoku",
    "Kyushu",
)


def area_sort_key(area: str) -> tuple[int, str]:
    """Canonical ordering for areas, used by both calculation output and presentation.

    Known areas sort in grid order; unknown areas sort alphabetically after them. A single
    ordering shared by the engine and the renderers keeps repeated runs byte-identical
    (requirements.md AC-01) without the two layers having to agree separately.
    """
    try:
        return (AREA_DISPLAY_ORDER.index(area), "")
    except ValueError:
        return (len(AREA_DISPLAY_ORDER), area)


@dataclass(frozen=True, slots=True)
class ReportingConfig:
    """Which reporting windows to produce.

    The brief deliberately leaves window starts, counts, and the week definition to the
    implementer (requirements.md S7, S17). They are therefore configuration rather than
    constants buried in calculation code, so that a desk preferring, say, six weeks of
    detail is a settings change and not a code change.
    """

    daily_count: int = 7
    """Calendar days from the as-of date inclusive (S7.1)."""

    weekly_count: int = 4
    """The current calendar week plus the following weekly_count - 1 weeks (S7.2)."""

    monthly_count: int = 12
    """The current calendar month plus the following monthly_count - 1 months (S7.3)."""

    week_start: int = calendar.MONDAY
    """First weekday of a reporting week, using date.weekday() numbering.

    Monday-to-Sunday is the chosen convention (S7.2). It is configurable because a desk
    reporting Sunday-start weeks is a plausible preference, not a different calculation.
    """

    def __post_init__(self) -> None:
        for field_name in ("daily_count", "weekly_count", "monthly_count"):
            count: int = getattr(self, field_name)
            if count < 1:
                raise ValueError(f"{field_name} must be at least 1, got {count}")
        if not 0 <= self.week_start <= 6:
            raise ValueError(
                f"week_start must be a date.weekday() value in 0..6, got {self.week_start}"
            )


DEFAULT_REPORTING_CONFIG = ReportingConfig()
"""The windows the assessment asks for: 7 days, 4 weeks, 12 months, Monday weeks."""

JST = "Asia/Tokyo"
"""All dates and times are interpreted in Japan Standard Time (S5.1).

Held as a label rather than a tzinfo because every boundary in scope falls at 00:00 JST
and Japan has no daylight saving, so no timezone arithmetic is performed. It is reported
in the output so the convention is never implicit (S8.1).
"""
