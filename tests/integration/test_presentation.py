"""Rendering: display rounding, the column contract, and machine output (S8.1, S8.3)."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from rich.console import Console

from app.config import DEFAULT_REPORTING_CONFIG, ReportingConfig
from app.core import Granularity, Position, TradeBook
from app.interfaces import console as console_view
from app.interfaces import json_out
from app.interfaces.console import Layout, _direction_changes
from app.interfaces.format import format_mw, format_mwh, position_text
from app.logging import RunDiagnostics
from app.services import RunResult, build_views
from tests.builders import AS_OF, make_trade, supplied_book
from tests.expected import SECTION_9_1_DAILY, SECTION_9_2_WEEKLY, SECTION_9_3_MONTHLY

pytestmark = pytest.mark.integration


class StubRepository:
    """A TradeRepository backed by an in-memory book."""

    def __init__(self, book: TradeBook) -> None:
        self._book = book

    @property
    def source(self) -> str:
        return "in-memory"

    def load(self) -> TradeBook:
        return self._book


def run(
    book: TradeBook | None = None,
    as_of: date = AS_OF,
    config: ReportingConfig | None = None,
) -> RunResult:
    return build_views(
        StubRepository(book if book is not None else supplied_book()),
        as_of,
        config or DEFAULT_REPORTING_CONFIG,
    )


def render_console(layout: Layout = Layout.LONG, **kwargs: object) -> str:
    """Render to a fixed-width, colourless console so output can be asserted on."""
    result = run(**kwargs)  # type: ignore[arg-type]
    buffer = StringIO()
    console = Console(file=buffer, width=200, no_color=True, legacy_windows=False)
    console_view.render(
        result.views, result.diagnostics, DEFAULT_REPORTING_CONFIG, console, layout
    )
    return buffer.getvalue()


class TestDisplayRounding:
    def test_average_mw_shows_two_places(self) -> None:
        assert format_mw(Decimal("27.714285714285714")) == "+27.71"
        assert format_mw(Decimal(30)) == "+30.00"

    def test_net_mwh_shows_whole_units_with_separators(self) -> None:
        assert format_mwh(Decimal(23_616)) == "+23,616"
        assert format_mwh(Decimal(-192)) == "-192"

    def test_zero_is_shown_without_a_sign(self) -> None:
        assert format_mwh(Decimal(0)) == "0"
        assert format_mw(Decimal(0)) == "0.00"

    def test_a_small_real_position_is_never_displayed_as_zero(self) -> None:
        """Otherwise a row would read "0 MWh" beside a LONG label and look like a bug."""
        assert format_mwh(Decimal("0.4")) == "+0.40"
        assert format_mwh(Decimal("-0.4")) == "-0.40"

    def test_rounding_is_half_up_not_bankers(self) -> None:
        """A reader checking a figure by hand expects half-up."""
        assert format_mwh(Decimal("0.5")) == "+1"
        assert format_mwh(Decimal("1.5")) == "+2"
        assert format_mw(Decimal("1.005")) == "+1.01"

    def test_rounding_happens_only_in_presentation(self) -> None:
        """S5.4: the engine's value stays unrounded; only the rendered string is rounded."""
        row = next(
            r
            for r in run().views[Granularity.MONTHLY]
            if r.area == "Tokyo" and r.period.label == "2026-10"
        )

        assert str(row.average_mw).startswith("31.7419")
        assert format_mw(row.average_mw) == "+31.74"


class TestPositionLabels:
    def test_every_position_shows_a_word_and_a_shape(self) -> None:
        """S8.3: colour must not be the only indicator, so neither may a glyph alone."""
        for position in Position:
            text = position_text(position)
            assert position.value in text
            assert len(text.split()) == 2

    def test_labels_appear_on_every_row_of_the_long_view(self) -> None:
        output = render_console()

        assert output.count("LONG") >= len(SECTION_9_1_DAILY)
        assert "FLAT" in output, "zero-exposure Kansai months must be labelled"


class TestConsoleContract:
    def test_states_the_as_of_date_timezone_and_sign_convention(self) -> None:
        """S8.1 requires these be stated globally, not left to documentation."""
        output = render_console()

        assert "2026-10-01" in output
        assert "Asia/Tokyo" in output
        assert "Buy = positive = long" in output
        assert "Sell = negative = short" in output
        assert "end date exclusive" in output

    def test_states_the_reporting_window_convention(self) -> None:
        output = render_console()

        assert "7 days, 4 weeks (Mon start), 12 months" in output
        assert "clipped at the as-of date" in output

    def test_names_average_mw_rather_than_mw(self) -> None:
        """S6.3: the column must not imply the exposure is constant over the period."""
        output = render_console()

        assert "Average MW" in output

    def test_keeps_the_three_views_visually_distinct(self) -> None:
        output = render_console()

        for title in ("Next 7 days", "Next 4 weeks", "Next 12 months"):
            assert title in output

    def test_omits_counterparty_and_price(self) -> None:
        """S8.3: irrelevant columns must not clutter the summary views."""
        output = render_console()

        assert "Sakura" not in output
        assert "13.50" not in output
        assert "Counterparty" not in output

    def test_marks_partial_periods_and_explains_the_marker(self) -> None:
        output = render_console()

        assert "2026-10-01 to 2026-10-04 *" in output
        assert "partial period" in output

    def test_monthly_rows_show_their_covered_dates(self) -> None:
        """A monthly label alone does not say where a clipped month starts (S8.1)."""
        output = render_console(as_of=date(2026, 10, 15))

        assert "2026-10-15 to 2026-10-31" in output

    def test_shows_every_expected_figure_from_section_9(self) -> None:
        output = render_console()

        for _, _, average_mw, net_mwh, _ in (
            *SECTION_9_1_DAILY,
            *SECTION_9_2_WEEKLY,
            *SECTION_9_3_MONTHLY,
        ):
            assert format_mw(Decimal(average_mw)) in output
            assert format_mwh(Decimal(net_mwh)) in output


class TestHeadline:
    def test_shows_a_total_per_area_per_horizon(self) -> None:
        output = render_console()

        assert "Where the book stands" in output
        assert "+187,296 MWh" in output, "Tokyo's 12-month total"
        assert "+5,040 MWh" in output, "Tokyo's 7-day total"

    def test_reports_a_change_of_direction(self) -> None:
        """The actionable signal: Kansai's Q4 position rolls off at the year end."""
        output = render_console()

        assert "Kansai turns FLAT from LONG at 2027-01" in output

    def test_finds_a_long_to_short_flip(self) -> None:
        book = TradeBook(
            (
                make_trade(trade_id="T001", volume_mw=10, start=AS_OF, end=date(2026, 10, 3)),
                make_trade(
                    trade_id="T002",
                    volume_mw=10,
                    direction=make_trade().direction.SELL,
                    start=date(2026, 10, 3),
                    end=date(2026, 10, 5),
                ),
            )
        )

        changes = _direction_changes(run(book).views)

        assert any(c.was is Position.LONG and c.now is Position.SHORT for c in changes)

    def test_says_so_when_nothing_changes_direction(self) -> None:
        book = TradeBook((make_trade(start=date(2026, 1, 1), end=date(2030, 1, 1)),))

        assert "No area changes direction" in render_console(book=book)

    def test_an_empty_book_says_so_rather_than_printing_empty_tables(self) -> None:
        output = render_console(book=TradeBook(()))

        assert "trade book is empty" in output


class TestMatrixLayout:
    def test_has_one_row_per_period_instead_of_one_per_area_and_period(self) -> None:
        long_output = render_console(Layout.LONG)
        matrix_output = render_console(Layout.MATRIX)

        assert matrix_output.count("2026-10-01 to 2026-10-04") < long_output.count(
            "2026-10-01 to 2026-10-04"
        )

    def test_pivots_areas_into_columns(self) -> None:
        output = render_console(Layout.MATRIX)

        assert "Net MWh by area" in output
        assert "Tokyo" in output and "Kansai" in output

    def test_carries_a_legend_for_its_glyphs(self) -> None:
        """It drops the written label for width, so the shapes must be decodable."""
        output = render_console(Layout.MATRIX)

        assert "Legend" in output
        assert "LONG" in output and "SHORT" in output and "FLAT" in output

    def test_points_at_the_views_that_carry_the_full_contract(self) -> None:
        output = render_console(Layout.MATRIX)

        assert "--layout long" in output and "--format json" in output


class TestJsonOutput:
    def test_is_valid_json_with_the_documented_structure(self) -> None:
        result = run()
        payload = json.loads(
            json_out.render(result.views, result.diagnostics, DEFAULT_REPORTING_CONFIG)
        )

        assert payload["as_of"] == "2026-10-01"
        assert payload["timezone"] == "Asia/Tokyo"
        assert payload["areas"] == ["Tokyo", "Kansai"]
        assert set(payload["views"]) == {"daily", "weekly", "monthly"}

    def test_states_its_conventions(self) -> None:
        payload = _payload()

        conventions = payload["conventions"]
        assert "Buy is positive" in conventions["sign"]
        assert conventions["delivery_interval"] == "start_date inclusive, end_date exclusive"
        assert conventions["reporting_windows"]["week_start_weekday"] == 0

    def test_includes_the_run_diagnostics(self) -> None:
        """S13.6 fields travel with the result rather than only reaching the log."""
        diagnostics = _payload()["diagnostics"]

        assert diagnostics["records_read"] == 12
        assert diagnostics["records_accepted"] == 12
        assert diagnostics["records_rejected"] == 0
        assert diagnostics["status"] == RunDiagnostics.COMPLETED

    def test_uses_exclusive_end_dates(self) -> None:
        """The machine form, labelled so it cannot be confused with the console's
        inclusive dates (S8.1)."""
        first = _payload()["views"]["daily"][0]

        assert first["period"]["start"] == "2026-10-01"
        assert first["period"]["end_exclusive"] == "2026-10-02"

    def test_is_long_format_regardless_of_console_layout(self) -> None:
        """One object per area and period: the S8.1 column contract."""
        payload = _payload()

        assert len(payload["views"]["daily"]) == len(SECTION_9_1_DAILY)
        assert len(payload["views"]["monthly"]) == len(SECTION_9_3_MONTHLY)

    def test_emits_net_mwh_exactly_as_a_string(self) -> None:
        """A JSON number would be read back as a binary float and lose exactness (S5.4)."""
        rows = _payload()["views"]["monthly"]
        tokyo = next(r for r in rows if r["area"] == "Tokyo" and r["period"]["label"] == "2026-10")

        assert tokyo["net_mwh"] == "23616"
        assert Decimal(tokyo["net_mwh"]) == Decimal(23_616)

    def test_matches_every_expected_net_mwh(self) -> None:
        payload = _payload()

        for name, expected in (
            ("daily", SECTION_9_1_DAILY),
            ("weekly", SECTION_9_2_WEEKLY),
            ("monthly", SECTION_9_3_MONTHLY),
        ):
            actual = [
                (r["period"]["label"], r["area"], Decimal(r["net_mwh"]))
                for r in payload["views"][name]
            ]
            assert actual == [(label, area, Decimal(mwh)) for label, area, _, mwh, _ in expected]

    def test_flags_partial_periods(self) -> None:
        weekly = _payload()["views"]["weekly"]

        assert weekly[0]["period"]["is_partial"] is True
        assert weekly[2]["period"]["is_partial"] is False

    def test_output_is_byte_identical_across_runs(self) -> None:
        """AC-01: the same inputs must serialise identically, so runs diff cleanly."""
        first = run()
        second = run()

        assert json_out.render(
            first.views, first.diagnostics, DEFAULT_REPORTING_CONFIG
        ) == json_out.render(second.views, second.diagnostics, DEFAULT_REPORTING_CONFIG)


def _payload() -> dict:  # type: ignore[type-arg]
    result = run()
    return json_out.to_payload(result.views, result.diagnostics, DEFAULT_REPORTING_CONFIG)


class TestReproducibility:
    def test_diagnostics_carry_no_timing_into_the_result(self) -> None:
        """AC-01: a measurement of the run must not make two identical runs differ.

        This also matters downstream: a snapshot identity derived from the payload would
        change on every refresh if timing leaked into it.
        """
        fields = run().diagnostics.as_fields()

        assert "duration_ms" not in fields
