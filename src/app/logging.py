"""Run diagnostics and how they are emitted.

requirements.md S13.6 lists what a run must make available. Those fields are a dataclass
rather than scattered log calls, so a run cannot report half of them, and so the same
record can later be served over HTTP without being rebuilt.

Diagnostics go to stderr and results go to stdout, so the output of a run can be piped
into another tool without log lines corrupting it.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date

LOGGER_NAME = "power_position"
_logger = logging.getLogger(LOGGER_NAME)


@dataclass(frozen=True, slots=True)
class RunDiagnostics:
    """What one run did (requirements.md S13.6)."""

    source: str
    as_of: date
    timezone: str
    records_read: int
    records_accepted: int
    records_rejected: int
    areas: tuple[str, ...]
    row_counts: dict[str, int]
    status: str
    duration_ms: float

    COMPLETED = "completed"
    FAILED = "failed"

    def as_fields(self) -> dict[str, object]:
        """The run record, excluding timing.

        ``duration_ms`` is deliberately left out: it is a measurement of the run, not a
        property of the result, and including it would make two runs over identical
        inputs produce different output, breaking the byte-for-byte reproducibility AC-01
        asks for. ``log_run`` adds it to the log line, where it belongs.

        No trade detail: S13.6 asks for counts, not a dump.
        """
        return {
            "status": self.status,
            "source": self.source,
            "as_of": self.as_of.isoformat(),
            "timezone": self.timezone,
            "records_read": self.records_read,
            "records_accepted": self.records_accepted,
            "records_rejected": self.records_rejected,
            "areas": ",".join(self.areas) or "(none)",
            **{f"rows_{name}": count for name, count in self.row_counts.items()},
        }


def configure_logging(verbose: bool = False) -> None:
    """Send diagnostics to stderr, leaving stdout for results."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    _logger.handlers.clear()
    _logger.addHandler(handler)
    _logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    _logger.propagate = False


def log_run(diagnostics: RunDiagnostics) -> None:
    """Emit the run record as one line of key=value pairs."""
    fields = {**diagnostics.as_fields(), "duration_ms": round(diagnostics.duration_ms, 1)}
    message = " ".join(f"{key}={value}" for key, value in fields.items())
    if diagnostics.status == RunDiagnostics.FAILED:
        _logger.error(message)
    else:
        _logger.info(message)


def log_failure(source: str, as_of: date, timezone: str, reason: str) -> None:
    """Emit a failure record when no successful run exists to describe."""
    _logger.error(
        f"status={RunDiagnostics.FAILED} source={source} as_of={as_of.isoformat()} "
        f"timezone={timezone} reason={reason}"
    )
