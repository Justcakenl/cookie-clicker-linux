"""The headless command line. Every flag here exits without starting Textual."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cookie import __version__, cli, instance, updater
from cookie.engine.content import ContentIndex
from cookie.engine.state import GameState
from cookie.persistence import paths
from cookie.persistence.store import SaveStore
from cookie.ui.theme import THEME_NAMES
from tests.conftest import EPOCH


def _seeded_save(directory: Path, state: GameState, content: ContentIndex) -> SaveStore:
    store = SaveStore(directory, content=content, app_version=__version__)
    state.all_time_cookies = 4_242.0
    state.run_cookies = 4_242.0
    state.owned = {"grandma": 7}
    state.revision += 1
    store.save(state, now=EPOCH)
    return store


def test_version_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_where_prints_the_save_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--save-dir", str(tmp_path), "--where"]) == 0
    assert capsys.readouterr().out.strip() == str(paths.save_path(tmp_path))


def test_where_reports_the_xdg_location_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "/srv/data")
    assert cli.main(["--where"]) == 0
    assert capsys.readouterr().out.strip() == "/srv/data/cookie/save.json"


def test_export_writes_the_current_save(
    tmp_path: Path, state: GameState, content: ContentIndex, capsys: pytest.CaptureFixture[str]
) -> None:
    _seeded_save(tmp_path / "data", state, content)
    destination = tmp_path / "out" / "backup.json"

    assert cli.main(["--save-dir", str(tmp_path / "data"), "--export", str(destination)]) == 0
    assert destination.exists()
    envelope = json.loads(destination.read_text(encoding="utf-8"))
    assert envelope["payload"]["state"]["all_time_cookies"] == 4_242.0
    assert str(destination) in capsys.readouterr().out


def test_export_with_no_save_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = cli.main(["--save-dir", str(tmp_path), "--export", str(tmp_path / "out.json")])
    assert result == 1
    assert "no save to export" in capsys.readouterr().err


def test_import_replaces_the_save_and_keeps_the_old_one(
    tmp_path: Path, state: GameState, content: ContentIndex, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    store = _seeded_save(data_dir, state, content)
    external = tmp_path / "elsewhere.json"
    state.all_time_cookies = 999_999.0
    state.run_cookies = 999_999.0
    state.revision += 1
    store.export_to(external, state, now=EPOCH)

    assert cli.main(["--save-dir", str(data_dir), "--import", str(external)]) == 0
    assert "imported" in capsys.readouterr().out

    reloaded = SaveStore(data_dir, content=content).load()
    assert reloaded.state.all_time_cookies == 999_999.0
    previous = json.loads(paths.backup_paths(data_dir)[0].read_bytes())
    assert previous["payload"]["state"]["all_time_cookies"] == 4_242.0


def test_importing_rubbish_is_refused_without_touching_the_save(
    tmp_path: Path, state: GameState, content: ContentIndex, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    _seeded_save(data_dir, state, content)
    junk = tmp_path / "junk.json"
    junk.write_text("definitely not a save", encoding="utf-8")

    assert cli.main(["--save-dir", str(data_dir), "--import", str(junk)]) == 1
    assert "cookie:" in capsys.readouterr().err
    assert SaveStore(data_dir, content=content).load().state.all_time_cookies == 4_242.0


def test_importing_a_missing_file_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--save-dir", str(tmp_path), "--import", str(tmp_path / "nope.json")]) == 1
    assert "cookie:" in capsys.readouterr().err


def test_the_parser_accepts_the_documented_flags() -> None:
    parsed = cli.build_parser().parse_args(["--save-dir", "/tmp/x", "--seed", "7", "--where"])
    assert parsed.save_dir == Path("/tmp/x")
    assert parsed.seed == 7
    assert parsed.where is True
    assert parsed.export is None
    assert parsed.import_from is None


def test_wipe_starts_over_and_keeps_the_previous_save(
    tmp_path: Path, state: GameState, content: ContentIndex, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    _seeded_save(data_dir, state, content)

    assert cli.main(["--save-dir", str(data_dir), "--wipe", "--yes"]) == 0
    out = capsys.readouterr().out
    assert "Wiped" in out

    reloaded = SaveStore(data_dir, content=content).load()
    assert reloaded.state.all_time_cookies == 0.0
    assert reloaded.state.owned == {}

    previous = json.loads(paths.backup_paths(data_dir)[0].read_bytes())
    assert previous["payload"]["state"]["all_time_cookies"] == 4_242.0


def test_wipe_keeps_settings(tmp_path: Path, state: GameState, content: ContentIndex) -> None:
    data_dir = tmp_path / "data"
    state.settings.number_format = "scientific"
    state.settings.theme = "night"
    _seeded_save(data_dir, state, content)

    assert cli.main(["--save-dir", str(data_dir), "--wipe", "--yes"]) == 0
    settings = SaveStore(data_dir, content=content).load().state.settings
    assert settings.number_format == "scientific"
    assert settings.theme == "night"


def test_wipe_with_no_save_says_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--save-dir", str(tmp_path), "--wipe", "--yes"]) == 0
    assert "no save to wipe" in capsys.readouterr().out


def test_wipe_refuses_without_confirmation_when_not_interactive(
    tmp_path: Path, state: GameState, content: ContentIndex, capsys: pytest.CaptureFixture[str]
) -> None:
    """Piping into it is not consent; the flag is."""
    data_dir = tmp_path / "data"
    _seeded_save(data_dir, state, content)

    assert cli.main(["--save-dir", str(data_dir), "--wipe"]) == 1
    assert "--yes" in capsys.readouterr().err
    assert SaveStore(data_dir, content=content).load().state.all_time_cookies == 4_242.0


def test_wipe_needs_the_word_typed_when_interactive(
    tmp_path: Path,
    state: GameState,
    content: ContentIndex,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    _seeded_save(data_dir, state, content)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    monkeypatch.setattr("builtins.input", lambda _prompt: "nope")
    assert cli.main(["--save-dir", str(data_dir), "--wipe"]) == 1
    assert SaveStore(data_dir, content=content).load().state.all_time_cookies == 4_242.0

    monkeypatch.setattr("builtins.input", lambda _prompt: "WIPE")
    assert cli.main(["--save-dir", str(data_dir), "--wipe"]) == 0
    assert SaveStore(data_dir, content=content).load().state.all_time_cookies == 0.0


def test_update_reports_being_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(updater, "plan", lambda current: _plan(current, current, installer="pipx"))
    assert cli.main(["--save-dir", str(tmp_path), "--update"]) == 0
    assert "Already up to date" in capsys.readouterr().out


def test_update_installs_after_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    applied: list[str] = []
    monkeypatch.setattr(updater, "plan", lambda current: _plan(current, "v9.9.9", installer="pipx"))
    monkeypatch.setattr(updater, "apply", lambda plan: applied.append(plan.release.tag))

    assert cli.main(["--save-dir", str(tmp_path), "--update", "--yes"]) == 0
    out = capsys.readouterr().out
    assert applied == ["v9.9.9"]
    assert "will not be touched" in out
    assert "Updated to v9.9.9" in out


def test_update_refuses_without_confirmation_when_not_interactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    applied: list[str] = []
    monkeypatch.setattr(updater, "plan", lambda current: _plan(current, "v9.9.9", installer="pipx"))
    monkeypatch.setattr(updater, "apply", lambda plan: applied.append(plan.release.tag))

    assert cli.main(["--save-dir", str(tmp_path), "--update"]) == 1
    assert applied == []
    assert "--yes" in capsys.readouterr().err


def test_update_reports_a_failure_rather_than_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(_current: str) -> updater.Plan:
        raise updater.UpdateError("could not reach GitHub: down")

    monkeypatch.setattr(updater, "plan", refuse)
    assert cli.main(["--save-dir", str(tmp_path), "--update"]) == 1
    assert "could not reach GitHub" in capsys.readouterr().err


def test_update_reports_a_failed_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(_plan: updater.Plan) -> int:
        raise updater.UpdateError("pipx exited with 1")

    monkeypatch.setattr(updater, "plan", lambda current: _plan(current, "v9.9.9", installer="pipx"))
    monkeypatch.setattr(updater, "apply", fail)
    assert cli.main(["--save-dir", str(tmp_path), "--update", "--yes"]) == 1
    assert "pipx exited with 1" in capsys.readouterr().err


def _plan(current: str, tag: str, *, installer: str) -> updater.Plan:
    release = updater.Release(tag=tag, url=f"https://github.com/owner/repo/releases/tag/{tag}")
    return updater.Plan(
        current=current,
        release=release,
        command=updater.install_command(tag, installer=installer, source="owner/repo"),
        installer=installer,
    )


def test_listing_themes_names_every_one(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--list-themes"]) == 0
    out = capsys.readouterr().out
    for name in THEME_NAMES:
        assert name in out
    assert "resolves to" in out, "system should say what it currently picks"


def test_setting_a_theme_persists_it_without_starting_the_game(
    tmp_path: Path, state: GameState, content: ContentIndex, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    _seeded_save(data_dir, state, content)

    assert cli.main(["--save-dir", str(data_dir), "--theme", "night"]) == 0
    assert "night" in capsys.readouterr().out
    reloaded = SaveStore(data_dir, content=content).load().state
    assert reloaded.settings.theme == "night"
    assert reloaded.all_time_cookies == 4_242.0, "setting a theme must not touch progress"


def test_setting_a_theme_on_a_fresh_install_creates_the_save(
    tmp_path: Path, content: ContentIndex
) -> None:
    assert cli.main(["--save-dir", str(tmp_path), "--theme", "terminal"]) == 0
    assert SaveStore(tmp_path, content=content).load().state.settings.theme == "terminal"


def test_setting_the_system_theme_reports_what_it_resolves_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("COLORFGBG", "0;15")
    assert cli.main(["--save-dir", str(tmp_path), "--theme", "system"]) == 0
    assert "resolves to day" in capsys.readouterr().out


def test_an_unknown_theme_is_refused_by_the_parser() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--theme", "neon"])
    assert exit_info.value.code == 2


def test_stats_prints_a_summary(
    tmp_path: Path, state: GameState, content: ContentIndex, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    state.total_clicks = 412
    _seeded_save(data_dir, state, content)

    assert cli.main(["--save-dir", str(data_dir), "--stats"]) == 0
    out = capsys.readouterr().out
    assert "Baked all time" in out
    assert "4.24 thousand" in out
    assert "412" in out
    assert f"of {len(content.achievements)}" not in out or "Achievements" in out


def test_stats_honours_the_number_format(
    tmp_path: Path, state: GameState, content: ContentIndex, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    state.settings.number_format = "raw"
    _seeded_save(data_dir, state, content)

    assert cli.main(["--save-dir", str(data_dir), "--stats"]) == 0
    assert "4,242" in capsys.readouterr().out


def test_stats_with_no_save_says_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--save-dir", str(tmp_path), "--stats"]) == 0
    assert "No save yet" in capsys.readouterr().out


def test_stop_reports_when_nothing_is_running(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--save-dir", str(tmp_path), "--stop"]) == 0
    assert "No game is running" in capsys.readouterr().out


def test_stop_signals_the_recorded_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    instance.write(paths.pid_path(tmp_path), pid=4_242)
    monkeypatch.setattr(instance, "command_line", lambda _pid: "cookie")

    sent: list[int] = []
    gone = [False]

    def kill(pid: int, sig: int) -> None:
        if sig == 0:
            if gone[0]:
                raise ProcessLookupError
            return
        sent.append(pid)
        gone[0] = True

    monkeypatch.setattr("os.kill", kill)
    assert cli.main(["--save-dir", str(tmp_path), "--stop"]) == 0
    assert sent == [4_242]
    assert "Stopped 4242" in capsys.readouterr().out
    assert not paths.pid_path(tmp_path).exists()


def test_stop_reports_a_process_that_will_not_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    instance.write(paths.pid_path(tmp_path), pid=4_242)
    monkeypatch.setattr(instance, "command_line", lambda _pid: "cookie")
    monkeypatch.setattr("os.kill", lambda _pid, _sig: None)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    assert cli.main(["--save-dir", str(tmp_path), "--stop"]) == 1
    assert "still running" in capsys.readouterr().err


def test_stop_clears_a_stale_claim(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A crashed instance leaves its pid behind. Stopping should tidy it, not report a phantom."""
    instance.write(paths.pid_path(tmp_path), pid=424_242)
    assert cli.main(["--save-dir", str(tmp_path), "--stop"]) == 0
    assert "No game is running" in capsys.readouterr().out
    assert not paths.pid_path(tmp_path).exists()
