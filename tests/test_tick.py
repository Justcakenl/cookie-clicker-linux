"""The tick contract: accumulation, boundedness, bulk catch-up, offline credit."""

from __future__ import annotations

import math

import pytest

from cookie.engine.content import ContentIndex
from cookie.engine.errors import InvalidStateError
from cookie.engine.specs import EffectSlot
from cookie.engine.state import ActiveEffect, GameState, GoldenPhase, new_game
from cookie.engine.tick import (
    BULK_THRESHOLD,
    FIXED_DT,
    MAX_STEPS_PER_CALL,
    OFFLINE_CAP,
    OFFLINE_MIN,
    OFFLINE_RATE,
    advance,
    apply_offline,
)
from tests.conftest import SEED

MONOTONE_FIELDS = (
    "all_time_cookies",
    "run_cookies",
    "time_played",
    "total_clicks",
    "prestige_count",
    "buildings_bought_total",
    "golden_cookies_caught",
    "golden_cookies_missed",
)


def _with_production(state: GameState, cps: float = 10.0) -> GameState:
    state.owned = {"grandma": int(cps)}
    state.revision += 1
    return state


def test_a_tick_bakes_cps_times_elapsed(state: GameState, content: ContentIndex) -> None:
    _with_production(state)
    result = advance(state, 1.0, content=content)
    assert result.steps_run == 10
    assert result.cookies_baked == pytest.approx(10.0)
    assert state.cookies == pytest.approx(10.0)
    assert state.all_time_cookies == pytest.approx(10.0)
    assert state.run_cookies == pytest.approx(10.0)
    assert state.time_played == pytest.approx(1.0)


def test_non_positive_elapsed_is_a_no_op(state: GameState, content: ContentIndex) -> None:
    _with_production(state)
    for elapsed in (0.0, -1.0, -1e9):
        result = advance(state, elapsed, content=content)
        assert result.steps_run == 0
        assert result.cookies_baked == 0.0
        assert state.cookies == 0.0
        assert state.time_played == 0.0


def test_non_finite_elapsed_is_rejected(state: GameState, content: ContentIndex) -> None:
    for elapsed in (math.nan, math.inf, -math.inf):
        with pytest.raises(InvalidStateError):
            advance(state, elapsed, content=content)


def test_partial_ticks_accumulate_exactly(state: GameState, content: ContentIndex) -> None:
    """Two half-ticks must be worth one tick, or a fast terminal would earn less than a slow one."""
    halves = _with_production(state)
    for _ in range(20):
        advance(halves, FIXED_DT / 2.0, content=content)

    whole = _with_production(new_game(seed=SEED, now=0.0))
    for _ in range(10):
        advance(whole, FIXED_DT, content=content)

    assert halves.cookies == pytest.approx(whole.cookies)
    assert halves.time_played == pytest.approx(whole.time_played)


def test_a_sub_tick_advance_banks_the_remainder(state: GameState, content: ContentIndex) -> None:
    _with_production(state)
    result = advance(state, 0.05, content=content)
    assert result.steps_run == 0
    assert state.tick_accumulator == pytest.approx(0.05)
    assert state.cookies == 0.0

    result = advance(state, 0.05, content=content)
    assert result.steps_run == 1
    assert state.cookies == pytest.approx(1.0)


def test_step_count_is_bounded_however_large_the_gap(
    state: GameState, content: ContentIndex
) -> None:
    _with_production(state)
    result = advance(state, 1e9, content=content)
    assert result.steps_run <= MAX_STEPS_PER_CALL
    assert result.bulk_seconds == pytest.approx(1e9 - BULK_THRESHOLD)


def test_bulk_integration_credits_cps_times_seconds(
    state: GameState, content: ContentIndex
) -> None:
    """With every multiplier already fixed, a long gap is worth exactly rate times time.

    The achievements are pre-unlocked on purpose: a live run earns some during the gap, which
    raises the rate partway through and is correct but makes the arithmetic unpinnable.
    """
    _with_production(state, cps=10.0)
    state.achievements_unlocked = {spec.id for spec in content.achievements}
    state.revision += 1
    rate = 10.0 * (1.0 + sum(spec.cps_bonus for spec in content.achievements))

    result = advance(state, 600.0, content=content)
    assert result.bulk_seconds == pytest.approx(600.0 - BULK_THRESHOLD)
    assert result.cookies_baked == pytest.approx(rate * 600.0, rel=1e-9)
    assert state.time_played == pytest.approx(600.0)


def test_bulk_integration_drops_timed_effects_and_reschedules(
    state: GameState, content: ContentIndex
) -> None:
    _with_production(state)
    state.active_effects = [ActiveEffect("gold_frenzy", EffectSlot.CPS_MULT, 7.0, 30.0)]
    state.revision += 1
    advance(state, 3_600.0, content=content)
    assert state.active_effects == []
    assert state.golden_phase is GoldenPhase.IDLE
    assert state.golden_next_spawn_at > state.time_played


def test_no_counter_ever_decreases(state: GameState, content: ContentIndex) -> None:
    _with_production(state)
    previous = {field: getattr(state, field) for field in MONOTONE_FIELDS}
    for elapsed in (0.1, 0.35, 5.0, 120.0, 0.05, 900.0):
        advance(state, elapsed, content=content)
        for field in MONOTONE_FIELDS:
            current = getattr(state, field)
            assert current >= previous[field], field
            previous[field] = current


def test_max_cps_seen_records_the_peak(state: GameState, content: ContentIndex) -> None:
    _with_production(state, cps=10.0)
    advance(state, 1.0, content=content)
    assert state.max_cps_seen == pytest.approx(10.0)

    state.owned = {"grandma": 1}
    state.revision += 1
    advance(state, 1.0, content=content)
    assert state.max_cps_seen == pytest.approx(10.0)


def test_offline_credits_half_rate_and_reports_it(state: GameState, content: ContentIndex) -> None:
    _with_production(state, cps=10.0)
    report = apply_offline(state, 3_600.0, content=content)
    assert report is not None
    assert report.cps_used == pytest.approx(10.0)
    assert report.credited_seconds == pytest.approx(3_600.0)
    assert report.cookies_awarded == pytest.approx(OFFLINE_RATE * 10.0 * 3_600.0)
    assert not report.capped
    assert state.cookies == pytest.approx(report.cookies_awarded)
    assert state.cookies_from_offline == pytest.approx(report.cookies_awarded)


def test_offline_does_not_advance_time_played(state: GameState, content: ContentIndex) -> None:
    """Otherwise a week away would bank golden cookies and buy time-played achievements."""
    _with_production(state)
    apply_offline(state, 604_800.0, content=content)
    assert state.time_played == 0.0
    assert state.golden_cookies_caught == 0


def test_offline_is_capped(state: GameState, content: ContentIndex) -> None:
    _with_production(state, cps=10.0)
    report = apply_offline(state, OFFLINE_CAP * 5.0, content=content)
    assert report is not None
    assert report.capped
    assert report.credited_seconds == pytest.approx(OFFLINE_CAP)
    assert report.cookies_awarded == pytest.approx(OFFLINE_RATE * 10.0 * OFFLINE_CAP)


def test_a_short_absence_awards_nothing_and_raises_no_screen(
    state: GameState, content: ContentIndex
) -> None:
    _with_production(state)
    assert apply_offline(state, OFFLINE_MIN - 0.01, content=content) is None
    assert apply_offline(state, 0.0, content=content) is None
    assert apply_offline(state, -5_000.0, content=content) is None
    assert state.cookies == 0.0


def test_offline_ignores_a_frenzy_that_was_running_at_quit(
    state: GameState, content: ContentIndex
) -> None:
    _with_production(state, cps=10.0)
    state.active_effects = [ActiveEffect("gold_frenzy", EffectSlot.CPS_MULT, 7.0, 30.0)]
    state.revision += 1
    report = apply_offline(state, 3_600.0, content=content)
    assert report is not None
    assert report.cps_used == pytest.approx(10.0)


def test_offline_with_no_production_awards_nothing(state: GameState, content: ContentIndex) -> None:
    report = apply_offline(state, 7_200.0, content=content)
    assert report is not None
    assert report.cookies_awarded == 0.0
