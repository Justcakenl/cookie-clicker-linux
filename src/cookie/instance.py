"""Finding and stopping a copy of the game that is already running.

A running game writes its pid beside its save and removes it on the way out. That is enough to let
`--stop` reach an instance left running in another terminal, and it sends SIGTERM rather than
SIGKILL so the instance takes its own shutdown path and saves first.

A pid file is a claim, not proof. It can outlive the process that wrote it, and the number can be
reused by something unrelated, so every read is checked against what the process actually is before
anything is signalled.
"""

from __future__ import annotations

import contextlib
import os
import signal
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

STOP_SIGNAL: Final[signal.Signals] = signal.SIGTERM
STOP_TIMEOUT: Final[float] = 5.0
POLL_INTERVAL: Final[float] = 0.1

Kill = Callable[[int, int], None]
Sleep = Callable[[float], None]


def _kill(override: Kill | None) -> Kill:
    """Resolve the signalling function at call time, not at import time.

    A default argument of `os.kill` would capture the function when this module is imported, which
    makes the real one unreachable afterwards and is a trap for anyone trying to observe it.
    """
    return os.kill if override is None else override


def write(path: Path, pid: int | None = None) -> None:
    """Claim this save directory for the current process."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(f"{os.getpid() if pid is None else pid}\n", encoding="utf-8")


def clear(path: Path) -> None:
    """Release the claim. Best effort: a missing file is the desired state."""
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


def read(path: Path) -> int | None:
    """The pid recorded in the file, or None when there is nothing usable in it."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        pid = int(raw)
    except ValueError:
        return None
    return pid if pid > 0 else None


def command_line(pid: int) -> str:
    """The process's command line, or an empty string when it cannot be read.

    Read from /proc, which is the only portable-enough answer on the target platform. An empty
    result means "cannot tell", and callers treat that as not-ours rather than guessing.
    """
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()


def looks_like_cookie(pid: int) -> bool:
    return "cookie" in command_line(pid)


def is_running(pid: int, *, kill: Kill | None = None) -> bool:
    """Whether a process with this pid exists and this user may signal it."""
    try:
        _kill(kill)(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # It exists and belongs to somebody else, which is not ours to stop.
        return False
    except OSError:
        return False
    return True


def running_pid(path: Path, *, kill: Kill | None = None) -> int | None:
    """The pid of a live instance that owns this save, or None.

    Returns None for a stale or foreign pid file, so a crashed instance cannot make `--stop` report
    a game that is not there.
    """
    pid = read(path)
    if pid is None or pid == os.getpid():
        return None
    if not is_running(pid, kill=kill):
        return None
    if not looks_like_cookie(pid):
        return None
    return pid


def stop(
    path: Path,
    *,
    kill: Kill | None = None,
    sleep: Sleep | None = None,
    timeout: float = STOP_TIMEOUT,
) -> int | None:
    """Ask a running instance to shut down, and wait for it to go.

    Returns the pid that was stopped, or None when nothing was running. SIGTERM, never SIGKILL: the
    instance has a shutdown path that settles the clock and saves, and skipping it to save a few
    seconds would throw away the progress this whole exercise is about.
    """
    pid = running_pid(path, kill=kill)
    if pid is None:
        clear(path)
        return None

    try:
        _kill(kill)(pid, STOP_SIGNAL)
    except OSError:
        return None

    wait = time.sleep if sleep is None else sleep
    deadline = timeout
    while deadline > 0.0 and is_running(pid, kill=kill):
        wait(POLL_INTERVAL)
        deadline -= POLL_INTERVAL
    clear(path)
    return pid
