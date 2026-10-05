"""Application orchestration: connect the input boundary, the calculation, and the clock.

requirements.md S14.9 makes this a boundary of its own. It is the only place that knows a
run consists of "load a book, then calculate views", which is what lets the CLI and (in a
later milestone) an HTTP adapter share one definition of a run.

Nothing here calculates or formats.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from time import perf_counter

from app.config import DEFAULT_REPORTING_CONFIG, JST, ReportingConfig
from app.core import PositionViews, calculate_views
from app.infrastructure import TradeRepository
from app.logging import RunDiagnostics


@dataclass(frozen=True, slots=True)
class RunResult:
    """Everything one run produced: the numbers, and the record of how they were made."""

    views: PositionViews
    diagnostics: RunDiagnostics


def build_views(
    repository: TradeRepository,
    as_of: date,
    config: ReportingConfig = DEFAULT_REPORTING_CONFIG,
    timezone: str = JST,
) -> RunResult:
    """Load the book and calculate every view as at ``as_of``.

    ``as_of`` is a required argument, never defaulted to today, so that the trade book
    plus the as-of value plus the configuration fully determine the result (S13.2).

    Raises:
        TradeSourceError: the trade source is unusable.
        TradeBookValidationError: the source is readable but its records are invalid.
    """
    started = perf_counter()
    book = repository.load()
    views = calculate_views(book, as_of, config)
    elapsed_ms = (perf_counter() - started) * 1000

    return RunResult(
        views=views,
        diagnostics=RunDiagnostics(
            source=repository.source,
            as_of=as_of,
            timezone=timezone,
            # An invalid record fails the whole run (S12), so a book that got this far is
            # complete: everything read was accepted and nothing was rejected.
            records_read=len(book),
            records_accepted=len(book),
            records_rejected=0,
            areas=views.areas,
            row_counts=views.row_counts,
            status=RunDiagnostics.COMPLETED,
            duration_ms=elapsed_ms,
        ),
    )
