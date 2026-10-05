"""The dependency rule, enforced rather than documented.

requirements.md S14 requires that core trade/profile/position logic not depend on CSV,
command-line, dataframe, or display concerns. That is the claim the whole design rests
on, so it is checked mechanically: a reviewer should not have to audit imports by hand,
and a later milestone cannot quietly break it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import app

pytestmark = pytest.mark.unit

CORE = Path(app.__file__).parent / "core"
FORBIDDEN_LAYERS = ("app.infrastructure", "app.interfaces", "app.services")
FORBIDDEN_LIBRARIES = (
    "csv",
    "pandas",
    "polars",
    "numpy",
    "pydantic",
    "typer",
    "click",
    "rich",
    "fastapi",
    "starlette",
    "argparse",
)


def _imported_modules(source: Path) -> set[str]:
    tree = ast.parse(source.read_text(), filename=str(source))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _core_modules() -> list[Path]:
    return sorted(CORE.glob("*.py"))


def test_core_package_was_found() -> None:
    """Guards the two tests below from silently passing on an empty file list."""
    assert _core_modules(), f"no core modules found under {CORE}"


@pytest.mark.parametrize("module", _core_modules(), ids=lambda p: p.name)
def test_core_does_not_depend_on_outer_layers(module: Path) -> None:
    offenders = {
        imported
        for imported in _imported_modules(module)
        if imported.startswith(FORBIDDEN_LAYERS)
    }

    assert not offenders, (
        f"{module.name} imports {sorted(offenders)}; the core must not depend on "
        f"infrastructure, interfaces, or services (requirements.md S14)"
    )


@pytest.mark.parametrize("module", _core_modules(), ids=lambda p: p.name)
def test_core_does_not_depend_on_io_or_presentation_libraries(module: Path) -> None:
    """S13.3: core calculations must run without the CSV parser, UI, or a dataframe."""
    offenders = {
        imported
        for imported in _imported_modules(module)
        if imported.split(".")[0] in FORBIDDEN_LIBRARIES
    }

    assert not offenders, (
        f"{module.name} imports {sorted(offenders)}; parsing, display, and transport "
        f"belong in the outer layers (requirements.md S13.3, S14)"
    )


@pytest.mark.parametrize("module", _core_modules(), ids=lambda p: p.name)
def test_core_never_reads_the_system_clock(module: Path) -> None:
    """S13.2: the as-of date must be injected, so results are fully determined by inputs."""
    source = module.read_text()
    for forbidden in ("date.today(", "datetime.now(", "datetime.utcnow(", "time.time("):
        assert forbidden not in source, (
            f"{module.name} calls {forbidden}); the as-of value must be passed in "
            f"explicitly (requirements.md S13.2)"
        )
