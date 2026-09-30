"""Save location resolution, including the XDG fallback."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cookie.persistence import paths


def test_xdg_data_home_is_used_when_absolute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "/srv/data")
    assert paths.data_dir() == Path("/srv/data/cookie")


def test_a_relative_xdg_data_home_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolving it against the working directory would put the save wherever the game started."""
    monkeypatch.setenv("XDG_DATA_HOME", "relative/path")
    assert paths.data_dir() == Path.home() / ".local" / "share" / "cookie"


def test_an_unset_or_empty_xdg_data_home_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert paths.data_dir() == Path.home() / ".local" / "share" / "cookie"
    monkeypatch.setenv("XDG_DATA_HOME", "")
    assert paths.data_dir() == Path.home() / ".local" / "share" / "cookie"


def test_candidates_are_the_save_then_three_backups_newest_first() -> None:
    directory = Path("/tmp/cookie")
    candidates = paths.load_candidates(directory)
    assert len(candidates) == 1 + paths.BACKUP_COUNT
    assert candidates[0] == directory / "save.json"
    assert [path.name for path in candidates[1:]] == [
        "save.json.bak.1",
        "save.json.bak.2",
        "save.json.bak.3",
    ]


def test_the_temp_file_is_process_scoped() -> None:
    """Two instances saving at once must not publish each other's half-written file."""
    assert paths.temp_path(Path("/tmp")).name == f"save.json.tmp.{os.getpid()}"


def test_the_corrupt_file_name_carries_a_timestamp() -> None:
    assert paths.corrupt_path(Path("/tmp"), now=1_774_000_000.9).name == (
        "save.json.corrupt.1774000000"
    )


def test_the_export_name_is_sortable() -> None:
    first = paths.export_name(now=1_774_000_000.0)
    later = paths.export_name(now=1_774_090_000.0)
    assert first.startswith("cookie-save-")
    assert first.endswith(".json")
    assert first < later
