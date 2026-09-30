"""The game session: the clock, the autosave timer, and the shutdown path.

This exists separately from the Textual app so that the promises that matter most — a save on quit,
a save on a signal, and offline credit on resume — can be tested without a terminal. The app owns
widgets; the session owns the state and the only clock reads in the program.
"""

from __future__ import annotations

import dataclasses
import enum
import sys
import threading
import time
from collections.abc import Callable
from typing import Final

from cookie import instance
from cookie.engine.content import CONTENT, ContentIndex
from cookie.engine.state import GameState, new_game
from cookie.engine.tick import OfflineReport, TickResult, advance, apply_offline
from cookie.persistence import paths
from cookie.persistence.store import LoadResult, LoadStatus, SaveError, SaveStore

AUTOSAVE_INTERVAL: Final[float] = 30.0

Monotonic = Callable[[], float]
WallClock = Callable[[], float]


class ShutdownReason(enum.StrEnum):
    QUIT = "quit"
    SIGNAL = "signal"
    ATEXIT = "atexit"


@dataclasses.dataclass(frozen=True, slots=True)
class StartReport:
    load: LoadResult
    offline: OfflineReport | None


class GameSession:
    """Owns the live state. One per process."""

    def __init__(
        self,
        store: SaveStore,
        *,
        content: ContentIndex = CONTENT,
        monotonic: Monotonic = time.monotonic,
        wall_clock: WallClock = time.time,
        seed: int | None = None,
    ) -> None:
        self._store = store
        self._content = content
        self._seed = seed
        self._monotonic = monotonic
        self._wall_clock = wall_clock
        self._lock = threading.RLock()
        self._state: GameState | None = None
        self._last_tick = 0.0
        self._last_autosave = 0.0
        self._shutting_down = False
        self._save_failure: str | None = None

    @property
    def content(self) -> ContentIndex:
        return self._content

    @property
    def store(self) -> SaveStore:
        return self._store

    def monotonic_now(self) -> float:
        """The monotonic clock, read through the session so tests can control it."""
        return self._monotonic()

    def wall_now(self) -> float:
        """The wall clock, read through the session so tests can control it."""
        return self._wall_clock()

    def adopt(self, state: GameState) -> None:
        """Replace the live state, after a hard reset or an import."""
        with self._lock:
            self._state = state

    @property
    def state(self) -> GameState:
        if self._state is None:
            raise RuntimeError("the session has not been started")
        return self._state

    @property
    def started(self) -> bool:
        return self._state is not None

    @property
    def save_failure(self) -> str | None:
        """The last save error, for the UI to surface. A failed save never stops the game."""
        return self._save_failure

    def start(self) -> StartReport:
        """Load, credit time away, and arm the clocks."""
        result = self._store.load(now=self._wall_clock())
        if result.status is LoadStatus.NEW_GAME and self._seed is not None:
            # A seed only applies to a game that is actually starting; it must never overwrite a
            # save, and an existing run keeps the seed it was created with.
            result = dataclasses.replace(
                result, state=new_game(seed=self._seed, now=self._wall_clock())
            )
        self._state = result.state
        offline = None
        if result.saved_at is not None:
            away = self._wall_clock() - result.saved_at
            offline = apply_offline(self._state, away, content=self._content)
        now = self._monotonic()
        self._last_tick = now
        self._last_autosave = now
        instance.write(paths.pid_path(self._store.directory))
        return StartReport(load=result, offline=offline)

    def tick(self) -> TickResult:
        """Advance by the real time since the last tick.

        The delta comes from a monotonic clock so that a system clock change cannot award or steal
        cookies, and `advance` clamps a long stall into one bulk integration rather than a freeze.
        """
        now = self._monotonic()
        elapsed = now - self._last_tick
        self._last_tick = now
        return advance(self.state, max(0.0, elapsed), content=self._content)

    def autosave_due(self) -> bool:
        return self._monotonic() - self._last_autosave >= AUTOSAVE_INTERVAL

    def save(self) -> bool:
        """Write the save. Returns False and records the reason if the write failed.

        A failed save is reported, never raised at the caller and never fatal: the previous save and
        its backups are still on disk, and taking the game down would only lose more.
        """
        with self._lock:
            try:
                self._store.save(self.state, now=self._wall_clock())
            except (SaveError, ValueError) as exc:
                self._save_failure = str(exc)
                return False
            self._last_autosave = self._monotonic()
            self._save_failure = None
            return True

    def autosave(self) -> bool | None:
        """Save if the interval has elapsed. Returns None when nothing was due."""
        if not self.autosave_due():
            return None
        return self.save()

    def shutdown(self, reason: ShutdownReason) -> bool:
        """Settle the clock, save, and refuse to run twice.

        Ordering matters: the final `tick` credits the seconds between the last frame and the
        signal, so the save is not stale, and `tick_accumulator` is left consistent.
        """
        with self._lock:
            if self._shutting_down or self._state is None:
                return False
            self._shutting_down = True
            instance.clear(paths.pid_path(self._store.directory))
            self.tick()
            if not self.save():
                # stderr is the only channel left once the UI is being torn down.
                print(
                    f"cookie: could not save on {reason}: {self._save_failure}",
                    file=sys.stderr,
                )
            return True

    @property
    def shutting_down(self) -> bool:
        return self._shutting_down
