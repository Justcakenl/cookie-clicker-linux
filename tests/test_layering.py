"""Invariant I-DEP of docs/ARCHITECTURE.md §1, enforced mechanically rather than by review."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "cookie"

ENGINE_FORBIDDEN = (
    "cookie.ui",
    "cookie.persistence",
    "cookie.app",
    "cookie.cli",
    "textual",
    "rich",
)
PERSISTENCE_FORBIDDEN = ("cookie.ui", "cookie.app", "cookie.cli", "textual", "rich")


def _imported_modules(tree: ast.AST) -> Iterator[str]:
    """Every module name imported anywhere in the file, including under TYPE_CHECKING."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            yield node.module


def _modules_under(subpackage: str) -> Iterator[tuple[Path, tuple[str, ...]]]:
    for path in sorted((PACKAGE_ROOT / subpackage).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        yield path, tuple(_imported_modules(tree))


def _top_level(module: str) -> str:
    return module.split(".", 1)[0]


def test_package_root_exists() -> None:
    assert PACKAGE_ROOT.is_dir(), f"expected the package at {PACKAGE_ROOT}"
    assert list((PACKAGE_ROOT / "engine").glob("*.py")), "no engine modules found to check"


def test_engine_imports_only_stdlib_and_engine() -> None:
    offenders: list[str] = []
    for path, imports in _modules_under("engine"):
        for module in imports:
            if module.startswith("cookie.engine") or module == "cookie":
                continue
            if _top_level(module) in sys.stdlib_module_names:
                continue
            offenders.append(f"{path.name} imports {module}")
    assert not offenders, "engine must import only the stdlib and itself: " + "; ".join(offenders)


def test_engine_never_imports_ui_persistence_or_textual() -> None:
    offenders: list[str] = []
    for path, imports in _modules_under("engine"):
        offenders.extend(
            f"{path.name} imports {module}"
            for module in imports
            if module.startswith(ENGINE_FORBIDDEN)
        )
    assert not offenders, "forbidden imports in engine: " + "; ".join(offenders)


def test_persistence_never_imports_ui_or_textual() -> None:
    if not (PACKAGE_ROOT / "persistence").is_dir():
        return
    offenders: list[str] = []
    for path, imports in _modules_under("persistence"):
        offenders.extend(
            f"{path.name} imports {module}"
            for module in imports
            if module.startswith(PERSISTENCE_FORBIDDEN)
        )
    assert not offenders, "forbidden imports in persistence: " + "; ".join(offenders)


def test_engine_never_reads_the_clock() -> None:
    """The engine takes elapsed time as an argument; only app.py and persistence read a clock."""
    offenders: list[str] = []
    for path in sorted((PACKAGE_ROOT / "engine").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("time.time(", "time.monotonic(", "datetime.now("):
            if forbidden in source:
                offenders.append(f"{path.name} calls {forbidden}")
    assert not offenders, "engine must not read a clock: " + "; ".join(offenders)


def test_engine_never_uses_the_global_rng() -> None:
    """All randomness goes through engine.rng, so that a seed fully determines a run."""
    offenders: list[str] = []
    for path in sorted((PACKAGE_ROOT / "engine").rglob("*.py")):
        if path.name == "rng.py":
            continue
        source = path.read_text(encoding="utf-8")
        for forbidden in ("random.random(", "random.uniform(", "random.choice(", "random.seed("):
            if forbidden in source:
                offenders.append(f"{path.name} calls {forbidden}")
    assert not offenders, "engine must draw through engine.rng: " + "; ".join(offenders)
