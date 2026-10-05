"""The result model: what a run produces, before any formatting.

Values here are unrounded. Rounding is a presentation decision applied at the very edge
(requirements.md S5.4), so that a weekly figure is never the sum of already-rounded daily
figures. Nothing in this module knows how a number will be displayed.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.core.periods import Granularity, ReportPeriod
from app.core.position import Position, classify


@dataclass(frozen=True, slots=True)
class PositionRow:
    """One area's net position over one reporting period.

    Carries the minimum columns S8.1 requires: area, period (label and covered dates via
    ``period``), Average MW, Net MWh, and a LONG/SHORT/FLAT label.
    """

    area: str
    period: ReportPeriod
    net_mwh: Decimal
    """Signed net energy over the period. Exact, and the canonical additive quantity (S6.3)."""

    average_mw: Decimal
    """Net MWh divided by the period's wall-clock hours (S6.3).

    A time-weighted average, not a constant exposure: a week containing a short-dated
    trade averages the days with and without it. This is why the column must be labelled
    "Average MW" and never "MW".
    """

    @property
    def position(self) -> Position:
        """LONG, SHORT, or FLAT.

        Derived on access rather than stored, so the label physically cannot disagree
        with the net MWh printed beside it (S6.4).
        """
        return classify(self.net_mwh)


@dataclass(frozen=True, slots=True)
class PositionView:
    """All rows for one granularity, ordered by period and then by area.

    Period-major ordering means a trader reads a day or a week as a contiguous block,
    which is how the expected results in S9 are laid out.
    """

    granularity: Granularity
    rows: tuple[PositionRow, ...]

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self) -> Iterator[PositionRow]:
        return iter(self.rows)


@dataclass(frozen=True, slots=True)
class PositionViews:
    """A complete run: the three views plus the context needed to read them.

    ``as_of`` and ``areas`` travel with the numbers because S8.1 requires the output to
    state its as-of date and because a trader needs to know which areas were considered
    in order to trust a FLAT row.
    """

    as_of: date
    areas: tuple[str, ...]
    views: tuple[PositionView, ...]

    def __getitem__(self, granularity: Granularity) -> PositionView:
        for view in self.views:
            if view.granularity is granularity:
                return view
        raise KeyError(granularity)

    def __iter__(self) -> Iterator[PositionView]:
        return iter(self.views)

    @property
    def row_counts(self) -> dict[str, int]:
        """Rows per view, for the run diagnostics S13.6 asks for."""
        return {view.granularity.value: len(view) for view in self.views}
