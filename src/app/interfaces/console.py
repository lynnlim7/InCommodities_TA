"""The trader-facing console view.

The brief's usability requirement is that the output be readable in under a minute
(requirements.md S2.1, S8.3). Three tables of raw rows do not achieve that on their own,
so the view opens with a headline block answering the two questions a trader asks first:
where am I long or short over each horizon, and does any position change direction inside
one? The detail tables follow for the row a trader then wants to check.

Contains no calculation. Every number here comes from a ``PositionRow``; this module only
groups, sorts, and formats (S13.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from itertools import pairwise

from rich.console import Console
from rich.table import Table
from rich.text import Text

from app.config import ReportingConfig
from app.core import (
    Granularity,
    Position,
    PositionRow,
    PositionView,
    PositionViews,
    classify,
)
from app.interfaces.format import (
    PARTIAL_MARKER,
    covered_dates,
    format_mw,
    format_mwh,
    period_label,
    position_legend,
    position_style,
    position_text,
)
from app.logging import RunDiagnostics

VIEW_TITLES = {
    Granularity.DAILY: "Next 7 days",
    Granularity.WEEKLY: "Next 4 weeks",
    Granularity.MONTHLY: "Next 12 months",
}
PERIOD_HEADERS = {
    Granularity.DAILY: "Date",
    Granularity.WEEKLY: "Week",
    Granularity.MONTHLY: "Month",
}
MAX_DIRECTION_CHANGES = 6
"""Headline changes are capped so the block stays scannable; the tables hold the rest."""


class Layout(Enum):
    """How to arrange the detail tables."""

    LONG = "long"
    """One row per area and period. The S8.1 column contract, and what S9 documents."""

    MATRIX = "matrix"
    """Areas pivoted into columns: one row per period instead of one per area and period.

    A scanning aid for a desk trading all nine areas, where the long view is 63 rows per
    table. It shows Net MWh only -- the additive quantity -- so Average MW and the written
    position label stay in the long view and the JSON output, which remain the complete
    contract.
    """


@dataclass(frozen=True, slots=True)
class DirectionChange:
    """A period where an area's position label differs from the preceding period's.

    This is the actionable signal in the whole report: a position rolling off, or flipping
    from long to short, is what makes a trader act.
    """

    granularity: Granularity
    area: str
    at_label: str
    was: Position
    now: Position


def render(
    views: PositionViews,
    diagnostics: RunDiagnostics,
    config: ReportingConfig,
    console: Console,
    layout: Layout = Layout.LONG,
) -> None:
    """Write the whole report."""
    _render_header(views, diagnostics, config, console)
    _render_headline(views, console)
    for view in views:
        console.print()
        if layout is Layout.MATRIX:
            console.print(_matrix_table(view, views.areas))
        else:
            console.print(_long_table(view))
    _render_footnotes(views, console, layout)


def _render_header(
    views: PositionViews, diagnostics: RunDiagnostics, config: ReportingConfig, console: Console
) -> None:
    """State every convention the numbers depend on (S8.1).

    Printed on every run rather than left to documentation, because a position table whose
    sign convention is unstated is ambiguous on its own.
    """
    week_name = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[config.week_start]
    console.print(
        Text("POWER POSITION", style="bold")
        + Text(f"   as of {diagnostics.as_of.isoformat()} ({diagnostics.timezone})")
    )
    console.print(
        f"[dim]Source[/dim] {diagnostics.source}   "
        f"[dim]Trades[/dim] {diagnostics.records_accepted}   "
        f"[dim]Areas[/dim] {', '.join(views.areas) or '(none)'}"
    )
    console.print(
        "[dim]Sign[/dim] Buy = positive = long, Sell = negative = short   "
        "[dim]Days[/dim] 00:00-00:00 JST, delivery end date exclusive"
    )
    console.print(
        f"[dim]Windows[/dim] {config.daily_count} days, {config.weekly_count} weeks "
        f"({week_name} start), {config.monthly_count} months, each clipped at the as-of date"
    )
    console.print(
        "[dim]Units[/dim] Net MWh is the additive period total; "
        "Average MW = Net MWh / hours in the period"
    )


def _render_headline(views: PositionViews, console: Console) -> None:
    """Totals per area per horizon, then any change of direction."""
    if not views.areas:
        console.print("\n[yellow]The trade book is empty: there is no position to report.[/yellow]")
        return

    table = Table(title="Where the book stands", title_justify="left", title_style="bold")
    table.add_column("Area")
    for view in views:
        table.add_column(VIEW_TITLES[view.granularity], justify="right")

    for area in views.areas:
        cells: list[str | Text] = [area]
        for view in views:
            total = sum((r.net_mwh for r in view if r.area == area), Decimal(0))
            position = classify(total)
            cells.append(
                Text(f"{format_mwh(total)} MWh  ", style="default")
                + Text(position_text(position), style=position_style(position))
            )
        table.add_row(*cells)

    console.print()
    console.print(table)

    changes = _direction_changes(views)
    if not changes:
        console.print("[dim]No area changes direction within any reported horizon.[/dim]")
        return

    console.print("[bold]Changes of direction[/bold]")
    for change in changes[:MAX_DIRECTION_CHANGES]:
        console.print(
            f"  {change.area} turns "
            f"[{position_style(change.now)}]{change.now.value}[/{position_style(change.now)}] "
            f"from {change.was.value} at {change.at_label} "
            f"({change.granularity.value})"
        )
    if len(changes) > MAX_DIRECTION_CHANGES:
        console.print(f"  [dim]...and {len(changes) - MAX_DIRECTION_CHANGES} more[/dim]")


def _direction_changes(views: PositionViews) -> list[DirectionChange]:
    """Find every period where an area's position label changes from the previous period."""
    changes: list[DirectionChange] = []
    for view in views:
        for area in views.areas:
            rows = [row for row in view if row.area == area]
            for previous, current in pairwise(rows):
                if current.position is not previous.position:
                    changes.append(
                        DirectionChange(
                            granularity=view.granularity,
                            area=area,
                            at_label=current.period.label,
                            was=previous.position,
                            now=current.position,
                        )
                    )
    return changes


def _shows_covered_dates(granularity: Granularity) -> bool:
    """Whether a separate covered-dates column is needed.

    S8.1 requires every row to show its covered start and end. For daily and weekly rows
    the period label already *is* those dates ("2026-10-01", "2026-10-05 to 2026-10-11"),
    so a second identical column would only consume width in a report meant to be scanned.
    A monthly label is "2026-10", which does not say where a clipped month starts, so
    those rows carry the dates explicitly.
    """
    return granularity is Granularity.MONTHLY


def _long_table(view: PositionView) -> Table:
    """One row per area and period: the S8.1 column contract."""
    table = Table(
        title=VIEW_TITLES[view.granularity],
        title_justify="left",
        title_style="bold",
    )
    show_covers = _shows_covered_dates(view.granularity)
    table.add_column(PERIOD_HEADERS[view.granularity])
    if show_covers:
        table.add_column("Covers")
    table.add_column("Area")
    table.add_column("Average MW", justify="right")
    table.add_column("Net MWh", justify="right")
    table.add_column("Position")

    for row in view:
        cells: list[str | Text] = [period_label(row.period)]
        if show_covers:
            cells.append(covered_dates(row.period))
        cells.extend(
            [
                row.area,
                format_mw(row.average_mw),
                format_mwh(row.net_mwh),
                Text(position_text(row.position), style=position_style(row.position)),
            ]
        )
        table.add_row(*cells)
    return table


def _matrix_table(view: PositionView, areas: tuple[str, ...]) -> Table:
    """Areas pivoted into columns, one row per period."""
    table = Table(
        title=f"{VIEW_TITLES[view.granularity]} - Net MWh by area",
        title_justify="left",
        title_style="bold",
    )
    show_covers = _shows_covered_dates(view.granularity)
    table.add_column(PERIOD_HEADERS[view.granularity])
    if show_covers:
        table.add_column("Covers")
    for area in areas:
        table.add_column(area, justify="right")

    by_period: dict[str, dict[str, PositionRow]] = {}
    order: list[str] = []
    for row in view:
        if row.period.label not in by_period:
            by_period[row.period.label] = {}
            order.append(row.period.label)
        by_period[row.period.label][row.area] = row

    for label in order:
        rows = by_period[label]
        any_row = next(iter(rows.values()))
        cells: list[str | Text] = [period_label(any_row.period)]
        if show_covers:
            cells.append(covered_dates(any_row.period))
        for area in areas:
            row = rows[area]
            cells.append(
                Text(
                    f"{format_mwh(row.net_mwh)} {position_text(row.position).split()[1]}",
                    style=position_style(row.position),
                )
            )
        table.add_row(*cells)
    return table


def _render_footnotes(views: PositionViews, console: Console, layout: Layout) -> None:
    notes: list[str] = []
    if layout is Layout.MATRIX:
        # The matrix trades the written label for width, so the shapes need decoding and
        # the reader needs pointing at the view that carries the full column contract.
        notes.append(
            f"Legend {position_legend()}   Average MW and the written position label are in "
            f"--layout long and --format json."
        )
    if any(row.period.is_partial for view in views for row in view):
        notes.append(
            f"{PARTIAL_MARKER} partial period: clipped at the as-of date, so its Net MWh "
            f"is not comparable with a full period's."
        )
    if notes:
        console.print()
        for note in notes:
            console.print(f"[dim]{note}[/dim]")
