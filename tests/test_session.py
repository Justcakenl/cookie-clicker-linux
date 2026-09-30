"""Session lifecycle: offline credit on resume, autosave cadence, and shutdown durability."""

from __future__ import annotations

from pathlib import Path

import pytest

from cookie.engine.content import ContentIndex
from cookie.persistence.store import LoadStatus, SaveStore
from cookie.session import AUTOSAVE_INTERVAL, GameSession, ShutdownReason
from tests.conftest import EPOCH


class FakeClock:
    """A clock the test moves by hand, so nothing here waits on real time."""

    def __init__(self, monotonic: float = 1_000.0, wall: float = EPOCH) -> None:
        self.monotonic_value = monotonic
        self.wall_value = wall

    def monotonic(self) -> float:
        return self.monotonic_value

    def wall(self) -> float:
        return self.wall_value

    def advance(self, seconds: float) -> None:
        self.monotonic_value += seconds
        self.wall_value += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def _fix_multipliers(session: GameSession, content: ContentIndex) -> float:
    """Ten Grandmas and every achievement already earned, so the rate cannot move mid-test.

    Returns the resulting rate, derived from the content tables rather than pinned, so adding an
    achievement does not break arithmetic that is not about achievements.
    """
    session.state.owned = {"grandma": 10}
    session.state.achievements_unlocked = {spec.id for spec in content.achievements}
    session.state.revision += 1
    return 10.0 * (1.0 + sum(spec.cps_bonus for spec in content.achievements))


def _session(tmp_path: Path, content: ContentIndex, clock: FakeClock) -> GameSession:
    store = SaveStore(tmp_path / "cookie", content=content, app_version="1.0.0")
    return GameSession(store, content=content, monotonic=clock.monotonic, wall_clock=clock.wall)


def test_a_first_run_starts_a_new_game_with_no_offline_credit(
    tmp_path: Path, content: ContentIndex, clock: FakeClock
) -> None:
    session = _session(tmp_path, content, clock)
    report = session.start()
    assert report.load.status is LoadStatus.NEW_GAME
    assert report.offline is None
    assert session.state.all_time_cookies == 0.0


def test_state_is_unavailable_before_start(
    tmp_path: Path, content: ContentIndex, clock: FakeClock
) -> None:
    session = _session(tmp_path, content, clock)
    assert not session.started
    with pytest.raises(RuntimeError, match="not been started"):
        _ = session.state


def test_ticking_credits_the_elapsed_monotonic_time(
    tmp_path: Path, content: ContentIndex, clock: FakeClock
) -> None:
    session = _session(tmp_path, content, clock)
    session.start()
    rate = _fix_multipliers(session, content)

    clock.advance(2.0)
    result = session.tick()
    assert result.steps_run == 20
    assert session.state.cookies == pytest.approx(rate * 2.0)


def test_a_backwards_monotonic_reading_credits_nothing(
    tmp_path: Path, content: ContentIndex, clock: FakeClock
) -> None:
    """Defensive rather than expected: a negative delta must not run the clock backwards."""
    session = _session(tmp_path, content, clock)
    session.start()
    session.state.owned = {"grandma": 10}
    session.state.revision += 1

    clock.monotonic_value -= 5.0
    result = session.tick()
    assert result.steps_run == 0
    assert session.state.cookies == 0.0


def test_autosave_waits_for_its_interval(
    tmp_path: Path, content: ContentIndex, clock: FakeClock
) -> None:
    session = _session(tmp_path, content, clock)
    session.start()
    assert session.autosave() is None

    clock.advance(AUTOSAVE_INTERVAL - 0.1)
    assert session.autosave() is None
    assert not session.store.save_path.exists()

    clock.advance(0.2)
    assert session.autosave() is True
    assert session.store.save_path.exists()

    assert session.autosave() is None


def test_resuming_credits_time_away_at_half_rate(
    tmp_path: Path, content: ContentIndex, clock: FakeClock
) -> None:
    session = _session(tmp_path, content, clock)
    session.start()
    session.state.owned = {"grandma": 10}
    session.state.revision += 1
    session.save()

    clock.advance(3_600.0)
    resumed = GameSession(
        session.store, content=content, monotonic=clock.monotonic, wall_clock=clock.wall
    )
    report = resumed.start()
    assert report.load.status is LoadStatus.OK
    assert report.offline is not None
    assert report.offline.cookies_awarded == pytest.approx(0.5 * 10.0 * 3_600.0)
    assert resumed.state.cookies == pytest.approx(report.offline.cookies_awarded)


def test_a_quick_restart_credits_nothing(
    tmp_path: Path, content: ContentIndex, clock: FakeClock
) -> None:
    session = _session(tmp_path, content, clock)
    session.start()
    session.state.owned = {"grandma": 10}
    session.state.revision += 1
    session.save()

    clock.advance(5.0)
    resumed = GameSession(
        session.store, content=content, monotonic=clock.monotonic, wall_clock=clock.wall
    )
    assert resumed.start().offline is None
    assert resumed.state.cookies == 0.0


def test_shutdown_settles_the_clock_before_saving(
    tmp_path: Path, content: ContentIndex, clock: FakeClock
) -> None:
    """The seconds between the last frame and the signal must be in the file, not lost."""
    session = _session(tmp_path, content, clock)
    session.start()
    rate = _fix_multipliers(session, content)

    clock.advance(4.0)
    assert session.shutdown(ShutdownReason.SIGNAL)

    reloaded = GameSession(
        session.store, content=content, monotonic=clock.monotonic, wall_clock=clock.wall
    ).start()
    assert reloaded.load.status is LoadStatus.OK
    assert reloaded.load.state.cookies == pytest.approx(rate * 4.0)
    assert reloaded.load.state.time_played == pytest.approx(4.0)


def test_shutdown_runs_once(tmp_path: Path, content: ContentIndex, clock: FakeClock) -> None:
    session = _session(tmp_path, content, clock)
    session.start()
    assert session.shutdown(ShutdownReason.QUIT) is True
    assert session.shutting_down
    assert session.shutdown(ShutdownReason.ATEXIT) is False


def test_shutdown_before_start_is_a_no_op(
    tmp_path: Path, content: ContentIndex, clock: FakeClock
) -> None:
    session = _session(tmp_path, content, clock)
    assert session.shutdown(ShutdownReason.ATEXIT) is False
    assert not session.store.save_path.exists()


def test_a_failed_save_is_reported_and_not_fatal(
    tmp_path: Path, content: ContentIndex, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _session(tmp_path, content, clock)
    session.start()

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError(13, "permission denied")

    monkeypatch.setattr(Path, "mkdir", refuse)
    assert session.save() is False
    assert session.save_failure is not None
    assert "permission denied" in session.save_failure
    monkeypatch.undo()

    assert session.save() is True
    assert session.save_failure is None


def test_shutdown_still_completes_when_the_save_fails(
    tmp_path: Path,
    content: ContentIndex,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = _session(tmp_path, content, clock)
    session.start()

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError(28, "no space left on device")

    monkeypatch.setattr(Path, "mkdir", refuse)
    assert session.shutdown(ShutdownReason.SIGNAL) is True
    assert "could not save on signal" in capsys.readouterr().err
