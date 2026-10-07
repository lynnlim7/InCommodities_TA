"""
Streamlit dashboard for Power Position Tool.

The dashboard serves as a reporting layer. 
Position calculation and trade aggregation are performed when the snapshot is loaded.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import os
from decimal import Decimal
from html import escape

import streamlit as st
import yaml
from pydantic import ValidationError

from app.adapters.csv_repository import DEFAULT_TRADES_CSV
from app.adapters.errors import TradeSourceError
from app.config.loader import AREAS_YAML, LOAD_PROFILES_YAML, TRADE_TYPES_YAML
from app.core.errors import PositionError
from app.core.models import ExcludedTrade, ReportingPeriod
from app.dashboard.formatting import (
    PositionState,
    format_energy,
    format_position,
    position_state,
)
from app.dashboard.snapshot import PositionView, Snapshot, load_snapshot

PAGE_TITLE = "Power Position"

# Points the dashboard at a different trade book, for a demo or a dry run,
# without editing code or the committed dataset.
TRADES_CSV_ENV = "POWER_POSITION_TRADES_CSV"

WARNING_SIGN = "\u26a0"
AREAS_PER_ROW = 3
AREA_COLUMN_WIDTH_PX = 620

# Hover text for table headers, so a column explains itself in place. Keyed by
# the header label exactly as it is rendered, which keeps the wording in one
# place and makes a missing hint obvious.
COLUMN_HINTS = {
    "Delivery": "The period this row covers, start date included, end date excluded.",
    "Net Position (MW)": "Average net power over the period: positive is long, negative is short.",
    "Net Position (MWh)": "Total net energy delivered over the period (average MW times hours).",
    "Trade": "The trade ID as it appears in the trade book.",
    "Product": (
        "The human-readable product string from the CSV. Shown for "
        "reconciliation only: the calculation never parses it."
    ),
    "Profile": (
        "The load profile that decides which hours of each day this trade "
        "delivers into (for example Base every hour, Peak weekday daytime)."
    ),
    "Direction": "Buy adds to the position, Sell subtracts from it.",
    "Quantity (MW)": (
        "The contractual MW on the trade, not time weighted. It cannot be "
        "summed down this column, which is why the hours are shown beside it."
    ),
    "Hours": (
        "The hours this trade actually delivers inside the reporting period, "
        "after its profile and delivery dates are applied."
    ),
    "Net Energy (MWh)": (
        "Signed energy this trade contributes. These do sum, to the period's "
        "reported net MWh above, across every load profile."
    ),
}


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

  /* Refresh time sits directly under the title: it is the first thing a desk
     checks before trusting a number on the screen. */
  .pp-header .pp-refreshed {
    font-size: .78rem;
    opacity: .55;
    margin-top: .3rem;
    font-variant-numeric: tabular-nums;
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

  /* A header carrying hover text advertises it with a dotted underline, so the
     tooltip is discoverable without adding an icon to every column. */
  table.pp-table th.pp-hint {
      cursor: help;
      text-decoration: underline dotted rgba(128,128,128,.6);
      text-underline-offset: 3px;
  }

  table.pp-table th.pp-hint:hover { opacity: .9; }


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


def _trades_csv() -> Path:
    """The trade book to load.

    Defaults to the book shipped in the package, and can be pointed at another
    file for a demo without touching the code or the committed dataset.
    """
    override = os.environ.get(TRADES_CSV_ENV)

    return Path(override) if override else DEFAULT_TRADES_CSV


def _source_mtimes(trades_csv: Path) -> tuple[float, ...]:
    """Modification times of every file a snapshot is built from.

    This is the cache key, so it has to name the configuration as well as the
    trade book: editing areas.yaml, trade_types.yaml or load_profiles.yaml
    changes the positions, and keying on the trade book alone would serve a
    stale snapshot until the CSV happened to change.
    """
    return tuple(
        _mtime(path)
        for path in (
            trades_csv,
            AREAS_YAML,
            TRADE_TYPES_YAML,
            LOAD_PROFILES_YAML,
        )
    )


def _mtime(path: Path) -> float:
    """Modification time, or zero when the file is missing.

    A missing file is reported by whichever loader needs it, with a message
    that names it. Raising here instead would attribute every missing file to
    the configuration.
    """
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


@st.cache_data(show_spinner="Loading trade book...")
def load_cached_snapshot(
    trades_csv: str,
    source_mtimes: tuple[float, ...],
) -> Snapshot:

    return load_snapshot(trades_csv=Path(trades_csv))

def render_dashboard(snapshot: Snapshot) -> None:
    """Render the complete position dashboard."""
    render_header(snapshot)
    render_data_quality(snapshot)
    render_legend()
    render_areas(snapshot)


def render_areas(snapshot: Snapshot) -> None:
    """Render every configured area side by side."""
    areas = snapshot.areas
    columns_per_row = min(len(areas), AREAS_PER_ROW)

    for start in range(0, len(areas), columns_per_row):
        row = areas[start : start + columns_per_row]

        columns = st.columns(columns_per_row, gap="large")

        for column, area in zip(columns, row, strict=False):
            with column:
                render_area(snapshot, area)


def render_header(snapshot: Snapshot) -> None:
    """Render the title, the refresh time, and the business reporting date."""
    st.markdown(
        (
            '<div class="pp-header">'
            "<div>"
            "<h1>Power Position</h1>"
            f'<div class="pp-refreshed">'
            f"Last refreshed: {snapshot.refreshed_at:%-d %b %Y, %H:%M} JST"
            "</div>"
            "</div>"
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
    """Render one reporting horizon for an area."""
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
            f"{_header_cell('Delivery')}"
            f"{_header_cell('Net Position (MW)', numeric=True)}"
            f"{_header_cell('Net Position (MWh)', numeric=True, sub=True)}"
        ),
        rows=rows,
    )


def _header_cell(
    label: str,
    *,
    numeric: bool = False,
    sub: bool = False,
) -> str:
    """One table header, carrying its explanation as hover text.

    The wording comes from ``COLUMN_HINTS``, so a column's meaning is defined
    once and every table that renders that header gets the same tooltip.
    """
    hint = COLUMN_HINTS.get(label)

    classes = " ".join(
        name
        for name, applies in (
            ("pp-num", numeric),
            ("pp-sub", sub),
            ("pp-hint", hint is not None),
        )
        if applies
    )

    title = f' title="{escape(hint)}"' if hint else ""

    return f"<th class='{classes}'{title}>{label}</th>"


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
            f"{_header_cell('Trade')}"
            f"{_header_cell('Product')}"
            f"{_header_cell('Profile')}"
            f"{_header_cell('Direction')}"
            f"{_header_cell('Quantity (MW)', numeric=True)}"
            f"{_header_cell('Hours', numeric=True)}"
            f"{_header_cell('Net Energy (MWh)', numeric=True)}"
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

    trades_csv = _trades_csv()

    try:
        snapshot = load_cached_snapshot(
            str(trades_csv),
            _source_mtimes(trades_csv),
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
