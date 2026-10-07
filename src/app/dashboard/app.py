"""
Streamlit dashboard for Power Presentation Tool.

The dashboard serves as a reporting layer. 
Position calculation and trade aggregation are performed when the snapshot is loaded.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit prepends the running script's own directory to sys.path. That
# directory is inside the `app` package and this file is itself named
# `app.py`, so the entry shadows the package and `import app.core` fails with
# "'app' is not a package". Putting `src` first makes the real package win.
# This must run before any `app.*` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decimal import Decimal
from html import escape

import streamlit as st
import yaml
from pydantic import ValidationError

from app.core.errors import PositionError
from app.core.models import ExcludedTrade, ReportingPeriod
from app.dashboard.format import (
    PositionState,
    format_energy,
    format_position,
    position_state,
)
from app.dashboard.snapshot import PositionView, Snapshot, load_snapshot
from app.infrastructure.csv_repository import DEFAULT_TRADES_CSV
from app.infrastructure.errors import TradeSourceError

PAGE_TITLE = "Power Position"

WARNING_SIGN = "\u26a0"

# Areas are shown side by side so the book is read across rather than by
# scrolling. Past this many, a position table gets too narrow to stay legible,
# so further areas wrap onto another row.
AREAS_PER_ROW = 3

# Comfortable reading width for one area's position table. The table carries a
# delivery label plus the MW and MWh readings, and the trade drill-down below
# it is wider still, so this leaves both room to breathe without wrapping.
AREA_COLUMN_WIDTH_PX = 620


STYLES = """
<style>
  .block-container {
      padding-top: 2.5rem;
      margin-left: auto;
      margin-right: auto;
  }

  .pp-header {
      display: flex; 
      align-items: baseline; 
      justify-content: space-between;
      border-bottom: 1px solid rgba(128,128,128,.35);
      padding-bottom: .5rem; 
      margin-bottom: 1.75rem;
  }

  .pp-header h1 { 
    font-size: 1.9rem; 
    font-weight: 650; 
    margin: 0; 
    letter-spacing: -.02em; 
    }

  .pp-header .pp-asof { 
    font-size: .95rem; 
    opacity: .75; 
    white-space: nowrap; 
    }

  .pp-area {
      display: flex; 
      align-items: center; 
      gap: 1rem;
      margin: 1.5rem 0 1rem; 
      text-transform: uppercase;
      font-size: .95rem; 
      font-weight: 650; 
      letter-spacing: .14em; 
      opacity: .85;
  }

  .pp-area::before, 
  .pp-area::after {
      content: ""; 
      flex: 1; 
      height: 1px; 
      background: rgba(128,128,128,.35);
  }

  .pp-view-title { 
  font-size: .95rem; 
  font-weight: 600; 
  margin: 1.1rem 0 .4rem; 
  }

  table.pp-table { 
  width: 100%; 
  border-collapse: collapse; 
  font-variant-numeric: tabular-nums; 
  }

  /* Rows never wrap, so on a narrow screen a table scrolls inside its own
     column rather than doubling every row's height or overlapping the next
     area. */
  .pp-scroll { overflow-x: auto; }

  table.pp-table th, table.pp-table td { white-space: nowrap; }

  table.pp-table th {
      text-align: left; 
      font-size: .72rem; 
      font-weight: 600;
      text-transform: uppercase; 
      letter-spacing: .07em; opacity: .6;
      padding: .3rem .5rem; 
      border-bottom: 1px solid rgba(128,128,128,.35);
  }

  table.pp-table th.pp-num, table.pp-table td.pp-num { text-align: right; }

  table.pp-table td {
      padding: .34rem .5rem; font-size: .9rem;
      border-bottom: 1px solid rgba(128,128,128,.14);
  }

  table.pp-table td.pp-num { font-weight: 600; }

  tr.pp-long  td { background: rgba(38, 125, 85, .13); }
  tr.pp-short td { background: rgba(165, 58, 58, .13); }

  tr.pp-incomplete td {
      background-image: repeating-linear-gradient(
          -45deg, rgba(196, 140, 30, .16) 0 6px, transparent 6px 12px);
  }

  .pp-flag {
      margin-left: .5rem;
      font-size: .72rem;
      font-weight: 600;
      color: rgb(176, 110, 10);
  }

  .pp-recon {
      font-size: .85rem;
      opacity: .8;
      margin: -1rem 0 1rem;
  }

  table.pp-table th.pp-sub, table.pp-table td.pp-sub {
      font-weight: 400;
      opacity: .7;
  }


  .pp-pos {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: .45rem;
  }

  .pp-val { min-width: 3.9rem; }

  .pp-dir {
      min-width: 3rem;
      text-align: left;
      font-size: .68rem;
      letter-spacing: .06em;
      opacity: .8;
  }

  .pp-legend {
      font-size: .8rem;
      opacity: .75;
      margin: -1rem 0 1.4rem;
  }

  .pp-legend + .pp-legend { margin-top: -1.1rem; }

  .pp-key {
      display: inline-block;
      width: .8rem;
      height: .8rem;
      border-radius: 2px;
      margin: 0 .35rem -.1rem 1rem;
  }

  .pp-key:first-child { margin-left: 0; }
  .pp-key-long  { background: rgba(38, 125, 85, .35); }
  .pp-key-short { background: rgba(165, 58, 58, .35); }
</style>
"""



ERROR_HINTS: tuple[tuple[type[Exception], str], ...] = (
    (
        TradeSourceError, 
        "The trade book could not be read, so no position was produced.",
    ),
    (
        PositionError, 
        "The position could not be calculated, so no position was produced.",
    ),
    (
        ValidationError, 
        "The application configuration is not valid.",
    ),
    (
        yaml.YAMLError, 
        "The application configuration could not be parsed.",
    ),
    (
        OSError, 
        "A configuration file could not be read.",
    ),
)

EXPECTED_ERRORS = tuple(error for error, _ in ERROR_HINTS)

@st.cache_data(show_spinner="Loading trade book...")
def load_cached_snapshot(trades_mtime: float) -> Snapshot:

    return load_snapshot()

def render_dashboard(snapshot: Snapshot) -> None:
    """Render the complete position dashboard."""
    render_header(snapshot)
    render_data_quality(snapshot)
    render_legend()
    render_areas(snapshot)
    render_footer(snapshot)


def render_areas(snapshot: Snapshot) -> None:
    """Render every configured area side by side.

    Areas share the same horizons in the same order, so placing them in
    columns lets the desk compare the same delivery period across areas on one
    line instead of scrolling between stacked sections.
    """
    areas = snapshot.areas
    columns_per_row = min(len(areas), AREAS_PER_ROW)

    for start in range(0, len(areas), columns_per_row):
        row = areas[start : start + columns_per_row]

        # Always build the full set of columns so every area keeps the same
        # width, even when the last row is not full.
        columns = st.columns(columns_per_row, gap="large")

        for column, area in zip(columns, row, strict=False):
            with column:
                render_area(snapshot, area)


def render_header(snapshot: Snapshot) -> None:
    """Render the dashboard title and business reporting date."""
    st.markdown(
        (
            '<div class="pp-header">'
            "<h1>Power Position</h1>"
            f'<div class="pp-asof">'
            f"{snapshot.as_of:%-d %b %Y}, {snapshot.as_of:%A}"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_area(snapshot: Snapshot, area: str) -> None:
    """Render all reporting horizons for one trading area."""
    st.markdown(
        f'<div class="pp-area">{area}</div>',
        unsafe_allow_html=True,
    )

    for view in snapshot.views:
        render_view(snapshot, view, area)


def render_view(
    snapshot: Snapshot,
    view: PositionView,
    area: str,
) -> None:
    """Render one reporting horizon for an area.

    Every load profile already nets into the area's hourly curve, so one
    table per horizon shows the whole position.
    """
    st.markdown(
        f'<div class="pp-view-title">{view.title}</div>',
        unsafe_allow_html=True,
    )

    render_position_table(snapshot, view, area)
    render_trade_drilldown(snapshot, view, area)


def render_position_table(
    snapshot: Snapshot,
    view: PositionView,
    area: str,
) -> None:
    """Render net positions for one reporting horizon."""
    rows = [
        _position_row(snapshot, view, area, period)
        for period in view.periods
    ]

    _render_table(
        headers=(
            "<th>Delivery</th>"
            "<th class='pp-num'>Net Position (MW)</th>"
            "<th class='pp-num pp-sub'>Net Position (MWh)</th>"
        ),
        rows=rows,
    )


def _position_row(
    snapshot: Snapshot,
    view: PositionView,
    area: str,
    period: ReportingPeriod,
) -> str:
    """Build one position-table row.

    MW and MWh are two readings of the same exposure: MW is the average rate
    over the period, MWh the energy it adds up to. They always share a sign,
    so one long/short classification colours and labels the whole row.
    """
    position = snapshot.position(
        area=area,
        period=period,
    )

    exposure = position.exposure
    state = position_state(exposure.net_mw)

    excluded = snapshot.excluded_trades(area=area, period=period)
    row_class = f"pp-{state} pp-incomplete" if excluded else f"pp-{state}"

    return (
        f'<tr class="{row_class}">'
        f"<td>{view.format_label(period.delivery)}{_incomplete_flag(excluded)}</td>"
        f'<td class="pp-num">{_position_cell(exposure.net_mw, state)}</td>'
        f'<td class="pp-num pp-sub">{format_energy(exposure.net_mwh)}</td>'
        "</tr>"
    )


def _incomplete_flag(excluded: tuple[ExcludedTrade, ...]) -> str:
    """Mark a position a quarantined trade could have moved."""

    if not excluded:
        return ""

    trade_ids = ", ".join(trade.trade_id or "unknown id" for trade in excluded)

    return (
        f'<span class="pp-flag" title="Quarantined: {escape(trade_ids)}">'
        f"{WARNING_SIGN} incomplete</span>"
    )


def _position_cell(
    net_mw: Decimal,
    state: PositionState,
) -> str:
    """Net MW with its direction in words, so a row reads without the colour."""
    return (
        '<div class="pp-pos">'
        f'<span class="pp-val">{format_position(net_mw)}</span>'
        f'<span class="pp-dir">{state.upper()}</span>'
        "</div>"
    )


def render_trade_drilldown(
    snapshot: Snapshot,
    view: PositionView,
    area: str,
) -> None:
    """Render a collapsed trade-level explanation for a selected position."""
    periods_by_label = {
        view.format_label(period.delivery): period
        for period in view.periods
    }

    widget_key = f"{area}-{view.title}"

    with st.expander("Explain a position", expanded=False):
        selected_label = st.selectbox(
            "Delivery period",
            options=list(periods_by_label),
            key=f"select-{widget_key}",
            label_visibility="collapsed",
        )

        render_contributions(
            snapshot=snapshot,
            area=area,
            period=periods_by_label[selected_label],
        )


def render_contributions(
    snapshot: Snapshot,
    area: str,
    period: ReportingPeriod,
) -> None:
    """Render trades contributing to a selected reporting period.

    Contractual MW cannot be summed down the column, so the hours that
    weighted each trade and the signed energy they produce are shown beside
    it. The MWh column does sum, to the period's reported net MWh above,
    across every load profile.
    """
    contributions = snapshot.contributions(
        area=area,
        period=period,
    )

    if not contributions:
        st.caption("No trades deliver into this period.")
        return

    rows = [
        (
            f"<tr>"
            f"<td>{contribution.trade.trade_id}</td>"
            f"<td>{contribution.trade.product}</td>"
            f"<td>{contribution.trade.load_profile}</td>"
            f"<td>{contribution.trade.buy_sell}</td>"
            f'<td class="pp-num">{contribution.trade.volume_mw:,.2f}</td>'
            f'<td class="pp-num">{contribution.applicable_hours:,.0f}</td>'
            f'<td class="pp-num">{format_energy(contribution.energy_mwh)}</td>'
            f"</tr>"
        )
        for contribution in contributions
    ]

    _render_table(
        headers=(
            "<th>Trade</th>"
            "<th>Product</th>"
            "<th>Profile</th>"
            "<th>Direction</th>"
            "<th class='pp-num'>Quantity (MW)</th>"
            "<th class='pp-num'>Hours</th>"
            "<th class='pp-num'>Net Energy (MWh)</th>"
        ),
        rows=rows,
    )


def render_legend() -> None:
    """Explain how to read a row once, under the header."""
    st.markdown(
        (
            '<div class="pp-legend">'
            '<span class="pp-key pp-key-long"></span>'
            "<b>LONG</b>: net bought, sell to reduce"
            '<span class="pp-key pp-key-short"></span>'
            "<b>SHORT</b>: net sold, buy to cover"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_data_quality(snapshot: Snapshot) -> None:
    """Reconcile the book and surface every quarantined trade."""

    result = snapshot.load_result
    quarantined = len(result.quarantined)

    st.markdown(
        (
            '<div class="pp-recon">'
            f"Trades Read: {result.rows_read:,} &nbsp;·&nbsp; "
            f"Counted: {len(result.trade_book):,} &nbsp;·&nbsp; "
            f"Quarantined: {quarantined:,}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    if not quarantined:
        return

    st.warning(
        f"**{quarantined} of {result.rows_read:,} trades were quarantined** "
        "and are not in the positions below. Positions they could have moved "
        f"are marked {WARNING_SIGN} incomplete until the trade book is fixed."
    )

    with st.expander("Quarantined trades"):
        st.code(
            "\n".join(
                str(error)
                for row in result.quarantined
                for error in row.errors
            ),
            language=None,
        )


def render_footer(snapshot: Snapshot) -> None:
    """Render snapshot refresh metadata."""
    st.markdown(
        (
            '<div style="margin-top:2.5rem;font-size:.8rem;opacity:.55">'
            f"Last refreshed: {snapshot.refreshed_at:%-d %b %Y, %H:%M} JST"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_table(*, headers: str, rows: list[str]) -> None:
    """Render a dashboard table using the shared table styling."""
    st.markdown(
        (
            '<div class="pp-scroll"><table class="pp-table">'
            f"<thead><tr>{headers}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table></div>"
        ),
        unsafe_allow_html=True,
    )


def _page_width_style(area_columns: int) -> str:
    """Widen the page to fit the areas shown side by side.

    Injected after the snapshot loads, because the width depends on how many
    areas are configured. One area keeps a comfortable reading measure rather
    than stretching a two-column table across the whole screen.
    """
    width = AREA_COLUMN_WIDTH_PX * area_columns

    return f"<style>.block-container{{max-width:{width}px;}}</style>"


def _render_expected_error(exc: Exception) -> None:
    """Render a user-facing message for an expected application failure."""
    hint = next(
        message
        for error_type, message in ERROR_HINTS
        if isinstance(exc, error_type)
    )

    st.error(f"**{hint}**\n\n```\n{exc}\n```")

def main() -> None:
    """Configure and run the Streamlit application."""
    st.set_page_config(
        page_title=PAGE_TITLE,
        layout="wide",
    )
    st.markdown(STYLES, unsafe_allow_html=True)

    try:
        snapshot = load_cached_snapshot(
            DEFAULT_TRADES_CSV.stat().st_mtime,
        )
    except EXPECTED_ERRORS as exc:
        _render_expected_error(exc)
        return

    st.markdown(
        _page_width_style(min(len(snapshot.areas), AREAS_PER_ROW)),
        unsafe_allow_html=True,
    )

    render_dashboard(snapshot)


main()
