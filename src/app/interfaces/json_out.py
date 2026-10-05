"""Machine-readable output.

Split into ``to_payload`` and ``render`` so that a later HTTP adapter can serve the same
structure without going through a string (requirements.md S14.8).

Two deliberate differences from the console view:

* End dates are **exclusive**, matching the data model, where the console shows inclusive
  dates for human readers. S8.1 allows either but forbids ambiguity, so each form is
  labelled: ``end_exclusive`` here, "Covers ... to ..." there.
* Every view is long-format -- one object per area and period -- regardless of the console
  layout, because that is the column contract S8.1 defines.

Numbers are emitted as strings. A JSON number would be read back as a binary float and
lose the exactness that S5.4 asks the pipeline to preserve; a string keeps ``23616`` and
``0.1`` intact for any consumer that parses them as decimals.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.config import ReportingConfig
from app.core import PositionViews
from app.logging import RunDiagnostics

AVERAGE_MW_PLACES = 6
"""Average MW is a repeating ratio, so it is emitted at six decimal places.

Net MWh is emitted exactly: it is the canonical additive quantity (S6.3) and a sum of
decimal volumes times integer hours, so it has a finite representation.
"""

_AVERAGE_MW_QUANTUM = Decimal(1).scaleb(-AVERAGE_MW_PLACES)


def to_payload(
    views: PositionViews, diagnostics: RunDiagnostics, config: ReportingConfig
) -> dict[str, Any]:
    """Build the output structure, including the conventions needed to read it (S8.1)."""
    return {
        "as_of": views.as_of.isoformat(),
        "timezone": diagnostics.timezone,
        "conventions": {
            "sign": "Buy is positive and long; Sell is negative and short",
            "delivery_interval": "start_date inclusive, end_date exclusive",
            "day_boundary": "00:00 JST",
            "net_mwh": "additive period total, emitted exactly",
            "average_mw": (
                f"net_mwh divided by the period's wall-clock hours, rounded to "
                f"{AVERAGE_MW_PLACES} decimal places"
            ),
            "period_end": "end_exclusive is the day after the last delivery day",
            "reporting_windows": {
                "daily_count": config.daily_count,
                "weekly_count": config.weekly_count,
                "monthly_count": config.monthly_count,
                "week_start_weekday": config.week_start,
                "partial_periods": "clipped at the as-of date and flagged is_partial",
            },
        },
        "diagnostics": diagnostics.as_fields(),
        "areas": list(views.areas),
        "views": {
            view.granularity.value: [
                {
                    "area": row.area,
                    "period": {
                        "label": row.period.label,
                        "granularity": row.period.granularity.value,
                        "start": row.period.start.isoformat(),
                        "end_exclusive": row.period.end_exclusive.isoformat(),
                        "is_partial": row.period.is_partial,
                        "hours": str(row.period.interval.hours),
                    },
                    "average_mw": str(
                        row.average_mw.quantize(_AVERAGE_MW_QUANTUM, rounding=ROUND_HALF_UP)
                    ),
                    "net_mwh": str(row.net_mwh),
                    "position": row.position.value,
                }
                for row in view
            ]
            for view in views
        },
    }


def render(views: PositionViews, diagnostics: RunDiagnostics, config: ReportingConfig) -> str:
    """Serialise the payload. Keys keep their declared order so runs diff cleanly (AC-01)."""
    return json.dumps(to_payload(views, diagnostics, config), indent=2, sort_keys=False)
