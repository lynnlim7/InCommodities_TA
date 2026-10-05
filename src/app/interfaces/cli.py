"""Command-line entry point.

Owns run-level error handling and exit status (requirements.md S14.9, S12). Internal
exceptions are never shown as the only explanation: each is translated into a concise,
actionable message, and the process exit code says which kind of failure occurred.

This is also the only module in the application permitted to read the system clock, and
even then only to resolve ``--as-of today``. The default is to require the date, so a run
recorded in a terminal transcript can always be reproduced (S13.2).
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from app.config import JST, ReportingConfig
from app.infrastructure import (
    DEFAULT_TRADES_CSV,
    CsvTradeRepository,
    InputError,
    TradeBookValidationError,
    TradeSourceError,
)
from app.interfaces import console as console_view
from app.interfaces import json_out
from app.interfaces.console import Layout
from app.logging import configure_logging, log_failure, log_run
from app.services import build_views

MAX_REPORTED_ERRORS = 25
"""Errors shown in full before summarising, so a badly broken file stays readable."""


class ExitCode(int, Enum):
    """Process exit status.

    Distinguished so a scheduled refresh can tell "point me at a different file" from
    "someone must correct a trade" without parsing the message.
    """

    OK = 0
    UNEXPECTED = 1
    INVALID_TRADE_DATA = 2
    UNREADABLE_SOURCE = 3


class OutputFormat(str, Enum):
    CONSOLE = "console"
    JSON = "json"


cli = typer.Typer(add_completion=False)


@cli.command()
def main(
    as_of: Annotated[
        str,
        typer.Option(
            "--as-of",
            help="Reporting date in YYYY-MM-DD (JST), or 'today'. Required: the core never "
            "reads the clock, so results stay reproducible.",
        ),
    ],
    input_path: Annotated[
        Path,
        typer.Option("--input", "-i", help="Trade book CSV."),
    ] = DEFAULT_TRADES_CSV,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="console for traders, json for machines."),
    ] = OutputFormat.CONSOLE,
    layout: Annotated[
        Layout,
        typer.Option(
            "--layout",
            help="long is one row per area and period; matrix pivots areas into columns.",
        ),
    ] = Layout.LONG,
    days: Annotated[int, typer.Option("--days", help="Daily periods to report.")] = 7,
    weeks: Annotated[int, typer.Option("--weeks", help="Weekly periods to report.")] = 4,
    months: Annotated[int, typer.Option("--months", help="Monthly periods to report.")] = 12,
    week_start: Annotated[
        int,
        typer.Option("--week-start", min=0, max=6, help="First weekday of a week; 0 is Monday."),
    ] = 0,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Also log the run diagnostics.")
    ] = False,
) -> None:
    """Show how many MW and MWh the desk is long or short, by delivery area.

    Reports the net position over the coming days, weeks, and months from a trade
    book CSV. Buy is long and positive, Sell is short and negative; all dates are
    JST and a delivery end date is exclusive.
    """
    configure_logging(verbose=verbose)
    stdout = Console()
    stderr = Console(stderr=True)

    reporting_date = _parse_as_of(as_of)
    config = _build_config(days, weeks, months, week_start, stderr)

    try:
        result = build_views(CsvTradeRepository(input_path), reporting_date, config)
    except TradeSourceError as exc:
        log_failure(str(input_path), reporting_date, JST, "unreadable source")
        stderr.print(f"[red]Cannot read the trade book.[/red] {exc}")
        raise typer.Exit(ExitCode.UNREADABLE_SOURCE) from None
    except TradeBookValidationError as exc:
        log_failure(str(input_path), reporting_date, JST, "invalid trade data")
        _report_validation_failure(exc, stderr)
        raise typer.Exit(ExitCode.INVALID_TRADE_DATA) from None
    except InputError as exc:
        log_failure(str(input_path), reporting_date, JST, "input error")
        stderr.print(f"[red]Input error.[/red] {exc}")
        raise typer.Exit(ExitCode.UNEXPECTED) from None

    if output_format is OutputFormat.JSON:
        # print, not Console.print: Rich would wrap and highlight the JSON.
        print(json_out.render(result.views, result.diagnostics, config))
    else:
        console_view.render(result.views, result.diagnostics, config, stdout, layout)

    log_run(result.diagnostics)


def _parse_as_of(value: str) -> date:
    """Resolve the as-of date, accepting 'today' as an explicit opt-in to the clock."""
    if value.strip().casefold() == "today":
        return date.today()
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise typer.BadParameter(
            f"{value!r} is not an ISO date; expected YYYY-MM-DD (for example 2026-10-01) "
            f"or 'today'",
            param_hint="--as-of",
        ) from None


def _build_config(
    days: int, weeks: int, months: int, week_start: int, stderr: Console
) -> ReportingConfig:
    try:
        return ReportingConfig(
            daily_count=days,
            weekly_count=weeks,
            monthly_count=months,
            week_start=week_start,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from None


def _report_validation_failure(exc: TradeBookValidationError, stderr: Console) -> None:
    """Show every problem found, so the file can be fixed in one edit (S12, AC-14)."""
    report = exc.report
    stderr.print(
        f"[red]The trade book is not valid, so no position was produced.[/red]\n"
        f"[dim]A partial book would still look like a complete position, and a position "
        f"missing trades can imply the wrong hedge.[/dim]\n"
        f"{exc.source}: {report.summary()}"
    )
    for row_error in report.errors[:MAX_REPORTED_ERRORS]:
        stderr.print(f"  {row_error}")
    remaining = len(report.errors) - MAX_REPORTED_ERRORS
    if remaining > 0:
        stderr.print(f"  [dim]...and {remaining} more problem(s)[/dim]")


def run() -> None:
    """Console-script entry point."""
    cli()


if __name__ == "__main__":  # pragma: no cover
    run()
