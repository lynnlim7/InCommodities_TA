"""Power Position dashboard.

Renders already-calculated positions. The pipeline runs once per data load in
``snapshot.py``; everything here is layout, formatting, and drill-down
presentation.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit prepends the running script's own directory to sys.path. That
# directory is inside the `app` package and this file is itself named
# `app.py`, so the entry shadows the package: `import app.core` resolves to
# this module and fails with "'app' is not a package". Putting `src` first
# makes the real package win. This must run before any `app.*` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import yaml
from pydantic import ValidationError

from app.core.errors import PositionError
from app.core.models import ReportingPeriod
from app.dashboard.format import (
    format_hours,
    format_position,
    position_state,
)
from app.dashboard.snapshot import (
    PositionView,
    Snapshot,
    load_snapshot,
)
from app.infrastructure.csv_repository import DEFAULT_TRADES_CSV
from app.infrastructure.errors import (
    TradeBookValidationError,
    TradeSourceError,
)

# Subtle fills only: the colour has to be readable at a glance without
# competing with the number it qualifies, and nothing else on the page is
# coloured.
STYLES = """
<style>
  .block-container {
      padding-top: 2.5rem; max-width: 1080px;
      margin-left: auto; margin-right: auto;
  }

  .pp-header {
      display: flex; align-items: baseline; justify-content: space-between;
      border-bottom: 1px solid rgba(128,128,128,.35);
      padding-bottom: .5rem; margin-bottom: 1.75rem;
  }
  .pp-header h1 { font-size: 1.9rem; font-weight: 650; margin: 0; letter-spacing: -.02em; }
  .pp-header .pp-asof { font-size: .95rem; opacity: .75; white-space: nowrap; }

  .pp-area {
      display: flex; align-items: center; gap: 1rem;
      margin: 1.5rem 0 1rem; text-transform: uppercase;
      font-size: .95rem; font-weight: 650; letter-spacing: .14em; opacity: .85;
  }
  .pp-area::before, .pp-area::after {
      content: ""; flex: 1; height: 1px; background: rgba(128,128,128,.35);
  }

  .pp-view-title { font-size: .95rem; font-weight: 600; margin: 1.1rem 0 .4rem; }

  table.pp-table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
  table.pp-table th {
      text-align: left; font-size: .72rem; font-weight: 600;
      text-transform: uppercase; letter-spacing: .07em; opacity: .6;
      padding: .3rem .7rem; border-bottom: 1px solid rgba(128,128,128,.35);
  }
  table.pp-table th.pp-num, table.pp-table td.pp-num { text-align: right; }
  table.pp-table td {
      padding: .34rem .7rem; font-size: .9rem;
      border-bottom: 1px solid rgba(128,128,128,.14);
  }
  table.pp-table td.pp-num { font-weight: 600; }

  tr.pp-long  td { background: rgba(38, 125, 85, .13); }
  tr.pp-short td { background: rgba(165, 58, 58, .13); }
</style>
"""

# Expected input and configuration failures, most specific first. The policy
# is to fail the whole run: a plausible-looking partial position could imply
# the wrong hedge. Anything not listed here is a defect and is allowed to
# surface as a traceback rather than being presented as bad input.
ERROR_HINTS: tuple[tuple[type[Exception], str], ...] = (
    (TradeBookValidationError, "The trade book is not valid, so no position was produced."),
    (TradeSourceError, "The trade book could not be read, so no position was produced."),
    (PositionError, "The trade book references unsupported reference data."),
    (ValidationError, "The application configuration is not valid."),
    (yaml.YAMLError, "The application configuration could not be parsed."),
    (OSError, "A configuration file could not be read."),
)

EXPECTED_ERRORS = tuple(error for error, _ in ERROR_HINTS)


def render_header(snapshot: Snapshot) -> None:
    """Title on the left, business reporting date on the right."""
    st.markdown(
        '<div class="pp-header">'
        "<h1>Power Position</h1>"
        f'<div class="pp-asof">As of: {snapshot.as_of:%-d %b %Y}, {snapshot.as_of:%A}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def render_position_table(
    snapshot: Snapshot,
    view: PositionView,
    area: str,
    load_profile: str,
) -> None:
    """One horizon as a two-column table, one row per reporting period.

    Rendered as a single table rather than per-row widgets so the trader can
    scan a whole horizon without the rows being pushed apart by controls.
    """
    rows = []

    for period in view.periods:
        net_position_mw = snapshot.net_position_mw(
            area=area,
            load_profile=load_profile,
            period=period,
        )
        rows.append(
            f'<tr class="pp-{position_state(net_position_mw)}">'
            f"<td>{view.format_label(period.delivery)}</td>"
            f'<td class="pp-num">{format_position(net_position_mw)}</td>'
            "</tr>"
        )

    st.markdown(
        '<table class="pp-table"><thead><tr>'
        "<th>Delivery</th><th class='pp-num'>Net Position (MW)</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>",
        unsafe_allow_html=True,
    )


def render_trade_drilldown(
    snapshot: Snapshot,
    view: PositionView,
    area: str,
    load_profile: str,
) -> None:
    """Collapsed explanation of any one row in the table above.

    One expander per table rather than per row: a row-level expander between
    every row would double the height of each horizon and work against
    scanning the L1 position, which is the dashboard's primary job.
    """
    labels = {view.format_label(period.delivery): period for period in view.periods}
    key = f"{area}-{load_profile}-{view.title}"

    with st.expander("Explain a position", expanded=False):
        label = st.selectbox(
            "Delivery period",
            options=list(labels),
            key=f"select-{key}",
            label_visibility="collapsed",
        )
        _render_contributions(snapshot, area, load_profile, labels[label])


def _render_contributions(
    snapshot: Snapshot,
    area: str,
    load_profile: str,
    period: ReportingPeriod,
) -> None:
    contributions = snapshot.contributions(
        area=area,
        load_profile=load_profile,
        period=period,
    )

    if not contributions:
        st.caption("No trades deliver into this period.")
        return

    rows = "".join(
        f"<tr><td>{contribution.trade.trade_id}</td>"
        f"<td>{contribution.trade.product}</td>"
        f"<td>{contribution.trade.buy_sell}</td>"
        f'<td class="pp-num">{contribution.trade.volume_mw:,.2f}</td>'
        f'<td class="pp-num">{format_hours(contribution.applicable_hours)}</td></tr>'
        for contribution in contributions
    )

    st.markdown(
        '<table class="pp-table"><thead><tr>'
        "<th>Trade</th><th>Product</th><th>Direction</th>"
        "<th class='pp-num'>Quantity (MW)</th>"
        "<th class='pp-num'>Applicable hours</th>"
        "</tr></thead><tbody>" + rows + "</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Quantity is the contractual MW of each trade. Trades covering different "
        "parts of the period are weighted by their applicable hours, so these "
        "quantities do not sum to the net position above."
    )


def render_view(snapshot: Snapshot, view: PositionView, area: str) -> None:
    """One horizon, with a tab per configured load profile.

    Base and Peak are different delivery shapes and are never added together,
    so each profile keeps its own table behind its own tab.
    """
    st.markdown(f'<div class="pp-view-title">{view.title}</div>', unsafe_allow_html=True)

    profile_names = snapshot.profile_names()

    if len(profile_names) == 1:
        render_position_table(snapshot, view, area, profile_names[0])
        render_trade_drilldown(snapshot, view, area, profile_names[0])
        return

    for tab, load_profile in zip(st.tabs(profile_names), profile_names, strict=True):
        with tab:
            render_position_table(snapshot, view, area, load_profile)
            render_trade_drilldown(snapshot, view, area, load_profile)


def render_area(snapshot: Snapshot, area: str) -> None:
    """One configured area: the same three horizons, in the same order."""
    st.markdown(f'<div class="pp-area">{area}</div>', unsafe_allow_html=True)

    for view in snapshot.views:
        render_view(snapshot, view, area)


@st.cache_data(show_spinner="Loading trade book...")
def _cached_snapshot(trades_mtime: float) -> Snapshot:
    """Load once and reuse across reruns of the same trade book.

    Keyed on the file's modification time so an edited book is picked up and
    the refresh timestamp stays truthful rather than reporting a stale load as
    current.
    """
    return load_snapshot()


def main() -> None:
    st.set_page_config(page_title="Power Position", layout="wide")
    st.markdown(STYLES, unsafe_allow_html=True)

    try:
        snapshot = _cached_snapshot(DEFAULT_TRADES_CSV.stat().st_mtime)
    except EXPECTED_ERRORS as exc:
        hint = next(message for error, message in ERROR_HINTS if isinstance(exc, error))
        st.error(f"**{hint}**\n\n```\n{exc}\n```")
        return

    render_header(snapshot)

    for area in snapshot.areas:
        render_area(snapshot, area)

    st.markdown(
        f'<div style="margin-top:2.5rem;font-size:.8rem;opacity:.55">'
        f"Last refreshed: {snapshot.refreshed_at:%-d %b %Y, %H:%M} JST</div>",
        unsafe_allow_html=True,
    )


main()
