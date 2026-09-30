"""Finding and stopping a running instance. A pid file is a claim, not proof."""

from __future__ import annotations

import os
import signal
from pathlib import Path

import pytest

from cookie import instance


def _refuse(_pid: int, _sig: int) -> None:
    raise ProcessLookupError


def _alive(_pid: int, _sig: int) -> None:
    return None


def test_a_claim_is_written_and_released(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "cookie.pid"
    instance.write(path)
    assert instance.read(path) == os.getpid()

    instance.clear(path)
    assert not path.exists()
    assert instance.read(path) is None


def test_clearing_a_missing_claim_is_not_an_error(tmp_path: Path) -> None:
    instance.clear(tmp_path / "cookie.pid")


@pytest.mark.parametrize("contents", ["", "   ", "not a number", "0", "-12", "12 34"])
def test_rubbish_in_the_file_reads_as_no_claim(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "cookie.pid"
    path.write_text(contents, encoding="utf-8")
    assert instance.read(path) is None


def test_a_stale_claim_is_not_a_running_game(tmp_path: Path) -> None:
    """A crashed instance leaves its pid behind; --stop must not report a game that is gone."""
    path = tmp_path / "cookie.pid"
    instance.write(path, pid=424_242)
    assert instance.running_pid(path, kill=_refuse) is None


def test_our_own_pid_is_never_treated_as_another_instance(tmp_path: Path) -> None:
    path = tmp_path / "cookie.pid"
    instance.write(path)
    assert instance.running_pid(path) is None


def test_a_live_pid_that_is_not_cookie_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pids are reused. Signalling one because a file named it would be somebody else's problem."""
    path = tmp_path / "cookie.pid"
    instance.write(path, pid=4_242)
    monkeypatch.setattr(instance, "command_line", lambda _pid: "/usr/bin/sshd -D")
    assert instance.running_pid(path, kill=_alive) is None


def test_a_live_cookie_is_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "cookie.pid"
    instance.write(path, pid=4_242)
    monkeypatch.setattr(instance, "command_line", lambda _pid: "/home/x/.local/bin/cookie")
    assert instance.running_pid(path, kill=_alive) == 4_242


def test_stopping_sends_a_term_and_waits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SIGTERM, not SIGKILL: the instance has a shutdown path that saves."""
    path = tmp_path / "cookie.pid"
    instance.write(path, pid=4_242)
    monkeypatch.setattr(instance, "command_line", lambda _pid: "cookie")

    sent: list[tuple[int, int]] = []
    remaining = [3]

    def kill(pid: int, sig: int) -> None:
        if sig == 0:
            if remaining[0] <= 0:
                raise ProcessLookupError
            return
        sent.append((pid, sig))

    def sleep(_seconds: float) -> None:
        remaining[0] -= 1

    assert instance.stop(path, kill=kill, sleep=sleep) == 4_242
    assert sent == [(4_242, signal.SIGTERM)]
    assert not path.exists(), "the claim is released once the process is gone"


def test_stopping_nothing_reports_nothing_and_tidies_up(tmp_path: Path) -> None:
    path = tmp_path / "cookie.pid"
    instance.write(path, pid=424_242)
    assert instance.stop(path, kill=_refuse, sleep=lambda _s: None) is None
    assert not path.exists()


def test_stopping_with_no_claim_at_all(tmp_path: Path) -> None:
    assert instance.stop(tmp_path / "cookie.pid", sleep=lambda _s: None) is None


def test_stopping_gives_up_after_the_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process that ignores SIGTERM is reported, not escalated to SIGKILL."""
    path = tmp_path / "cookie.pid"
    instance.write(path, pid=4_242)
    monkeypatch.setattr(instance, "command_line", lambda _pid: "cookie")
    slept: list[float] = []

    assert instance.stop(path, kill=_alive, sleep=slept.append, timeout=0.5) == 4_242
    assert slept, "it should have waited before giving up"
    assert sum(slept) == pytest.approx(0.6, abs=instance.POLL_INTERVAL)


def test_a_permission_error_means_not_ours_to_stop() -> None:
    def forbidden(_pid: int, _sig: int) -> None:
        raise PermissionError

    assert not instance.is_running(4_242, kill=forbidden)


def test_the_command_line_of_a_missing_process_is_empty() -> None:
    assert instance.command_line(424_242) == ""


def test_this_process_recognises_itself() -> None:
    """The /proc read has to actually work on the target platform, not just not raise."""
    assert instance.command_line(os.getpid())
    assert instance.is_running(os.getpid())
