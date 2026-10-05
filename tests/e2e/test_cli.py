"""The application as a user invokes it (requirements.md S15.3).

Run as a real subprocess rather than through Typer's test runner, so exit codes, the
stdout/stderr split, and the console script wiring are all exercised as shipped.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from app.infrastructure import CSV_HEADERS, DEFAULT_TRADES_CSV
from tests.expected import SECTION_9_1_DAILY, SECTION_9_2_WEEKLY, SECTION_9_3_MONTHLY

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]

OK = 0
UNEXPECTED = 1
INVALID_TRADE_DATA = 2
UNREADABLE_SOURCE = 3

VALID_ROW = [
    "T001",
    "2026-09-10",
    "Sakura Power Trading",
    "Tokyo",
    "Futures",
    "Buy",
    "Oct-26 Base",
    "Base",
    "2026-10-01",
    "2026-11-01",
    "20",
    "13.50",
]


@dataclass(frozen=True)
class Run:
    exit_code: int
    stdout: str
    stderr: str


def invoke(*args: str) -> Run:
    """Run the CLI in a clean subprocess with a fixed terminal width."""
    env = {
        **os.environ,
        # src on the path directly: the suite must not depend on the editable install
        # resolving, which is environment-specific.
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "COLUMNS": "200",
        "NO_COLOR": "1",
        "TERM": "dumb",
    }
    completed = subprocess.run(
        [sys.executable, "-m", "app.interfaces.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
        timeout=120,
    )
    return Run(completed.returncode, completed.stdout, completed.stderr)


def write_csv(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADERS)
        writer.writerows(rows)
    return path


class TestSuccessfulRun:
    def test_exits_zero_with_the_supplied_book(self) -> None:
        result = invoke("--as-of", "2026-10-01")

        assert result.exit_code == OK, result.stderr

    def test_produces_all_three_labelled_views(self) -> None:
        result = invoke("--as-of", "2026-10-01")

        for title in ("Next 7 days", "Next 4 weeks", "Next 12 months"):
            assert title in result.stdout

    def test_states_its_as_of_date_timezone_and_conventions(self) -> None:
        result = invoke("--as-of", "2026-10-01")

        assert "as of 2026-10-01 (Asia/Tokyo)" in result.stdout
        assert "Buy = positive = long" in result.stdout

    def test_every_expected_figure_appears(self) -> None:
        """AC-09, AC-10, AC-11 through the shipped entry point."""
        result = invoke("--as-of", "2026-10-01")

        for _, _, _, net_mwh, position in (
            *SECTION_9_1_DAILY,
            *SECTION_9_2_WEEKLY,
            *SECTION_9_3_MONTHLY,
        ):
            assert f"{net_mwh:+,}" in result.stdout or net_mwh == 0
            assert position in result.stdout

    def test_diagnostics_go_to_stderr_leaving_stdout_clean(self) -> None:
        """So a run can be piped into another tool without log lines corrupting it."""
        result = invoke("--as-of", "2026-10-01")

        assert "status=completed" in result.stderr
        assert "status=completed" not in result.stdout

    def test_diagnostics_report_every_field_the_specification_asks_for(self) -> None:
        result = invoke("--as-of", "2026-10-01")

        for field in (
            "status=completed",
            "as_of=2026-10-01",
            "timezone=Asia/Tokyo",
            "records_read=12",
            "records_accepted=12",
            "records_rejected=0",
            "areas=Tokyo,Kansai",
            "rows_daily=14",
            "rows_weekly=8",
            "rows_monthly=24",
        ):
            assert field in result.stderr, field

    def test_repeated_runs_produce_identical_output(self) -> None:
        """AC-01: repeated runs on the same inputs are byte-identical."""
        first = invoke("--as-of", "2026-10-01", "--format", "json")
        second = invoke("--as-of", "2026-10-01", "--format", "json")

        assert first.stdout == second.stdout

    def test_matrix_layout_is_available(self) -> None:
        result = invoke("--as-of", "2026-10-01", "--layout", "matrix")

        assert result.exit_code == OK
        assert "Net MWh by area" in result.stdout
        assert "Legend" in result.stdout

    def test_explicit_input_path_is_honoured(self) -> None:
        result = invoke("--as-of", "2026-10-01", "--input", str(DEFAULT_TRADES_CSV))

        assert result.exit_code == OK
        assert str(DEFAULT_TRADES_CSV) in result.stdout

    def test_window_counts_are_configurable_from_the_command_line(self) -> None:
        result = invoke("--as-of", "2026-10-01", "--days", "2", "--weeks", "1", "--months", "1")

        assert result.exit_code == OK
        assert "rows_daily=4" in result.stderr, "2 days x 2 areas"
        assert "rows_weekly=2" in result.stderr
        assert "rows_monthly=2" in result.stderr


class TestJsonFormat:
    def test_stdout_is_parseable_json(self) -> None:
        result = invoke("--as-of", "2026-10-01", "--format", "json")

        payload = json.loads(result.stdout)
        assert payload["as_of"] == "2026-10-01"

    def test_json_reproduces_every_expected_figure(self) -> None:
        result = invoke("--as-of", "2026-10-01", "--format", "json")
        payload = json.loads(result.stdout)

        for name, expected in (
            ("daily", SECTION_9_1_DAILY),
            ("weekly", SECTION_9_2_WEEKLY),
            ("monthly", SECTION_9_3_MONTHLY),
        ):
            rows = payload["views"][name]
            assert [
                (r["period"]["label"], r["area"], Decimal(r["net_mwh"]), r["position"])
                for r in rows
            ] == [(label, area, Decimal(mwh), pos) for label, area, _, mwh, pos in expected]


class TestFailureModes:
    def test_missing_file_exits_three(self) -> None:
        result = invoke("--as-of", "2026-10-01", "--input", "does-not-exist.csv")

        assert result.exit_code == UNREADABLE_SOURCE
        assert "not found" in result.stderr
        assert result.stdout == ""

    def test_wrong_columns_exits_three(self, tmp_path: Path) -> None:
        target = tmp_path / "wrong.csv"
        target.write_text("a,b,c\n1,2,3\n", encoding="utf-8")

        result = invoke("--as-of", "2026-10-01", "--input", str(target))

        assert result.exit_code == UNREADABLE_SOURCE
        assert "wrong columns" in result.stderr

    def test_invalid_data_exits_two_and_produces_no_position(self, tmp_path: Path) -> None:
        """AC-14: invalid rows are not silently discarded, and no partial book is shown."""
        bad = list(VALID_ROW)
        bad[10] = "-5"
        target = write_csv(tmp_path / "bad.csv", [bad])

        result = invoke("--as-of", "2026-10-01", "--input", str(target))

        assert result.exit_code == INVALID_TRADE_DATA
        assert result.stdout == "", "no position may be produced from an invalid book"
        assert "not valid" in result.stderr

    def test_the_failure_names_row_field_value_and_reason(self, tmp_path: Path) -> None:
        bad = list(VALID_ROW)
        bad[5] = "Short"
        target = write_csv(tmp_path / "direction.csv", [bad])

        result = invoke("--as-of", "2026-10-01", "--input", str(target))

        assert "line 2" in result.stderr
        assert "trade T001" in result.stderr
        assert "buy_sell" in result.stderr
        assert "Short" in result.stderr
        assert "Buy, Sell" in result.stderr

    def test_every_problem_is_reported_in_one_run(self, tmp_path: Path) -> None:
        first, second = list(VALID_ROW), list(VALID_ROW)
        first[10] = "0"
        second[0], second[3] = "T002", ""
        target = write_csv(tmp_path / "many.csv", [first, second])

        result = invoke("--as-of", "2026-10-01", "--input", str(target))

        assert "2 problem(s) in 2 of 2 row(s)" in result.stderr
        assert "volume_mw" in result.stderr
        assert "area" in result.stderr

    def test_a_failed_run_is_logged_as_failed(self, tmp_path: Path) -> None:
        result = invoke("--as-of", "2026-10-01", "--input", str(tmp_path / "absent.csv"))

        assert "status=failed" in result.stderr

    def test_as_of_is_required(self) -> None:
        """S13.2: the core never reads the clock, so the date must be supplied."""
        result = invoke()

        assert result.exit_code != OK
        assert "--as-of" in result.stderr

    def test_a_malformed_as_of_is_rejected_with_an_example(self) -> None:
        result = invoke("--as-of", "01/10/2026")

        assert result.exit_code != OK
        assert "2026-10-01" in result.stderr, "the message should show the expected form"

    def test_a_zero_window_count_is_rejected(self) -> None:
        result = invoke("--as-of", "2026-10-01", "--days", "0")

        assert result.exit_code != OK
        assert "daily_count" in result.stderr


class TestHelp:
    def test_help_describes_the_tool(self) -> None:
        result = invoke("--help")

        assert result.exit_code == OK
        assert "long or short" in result.stdout
