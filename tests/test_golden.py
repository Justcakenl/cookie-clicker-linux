"""Golden cookie state machine and schedule determinism, per docs/ARCHITECTURE.md §7."""

from __future__ import annotations

import pytest

from cookie.engine import golden, rng
from cookie.engine.actions import catch_golden
from cookie.engine.content import CONTENT, ContentIndex
from cookie.engine.derive import derive
from cookie.engine.specs import EffectSlot
from cookie.engine.state import (
    GOLDEN_INTERVAL_MAX,
    GOLDEN_INTERVAL_MIN,
    GOLDEN_LIFETIME,
    ActiveEffect,
    GameState,
    GoldenPhase,
    new_game,
)
from cookie.engine.tick import FIXED_DT, advance
from tests.conftest import SEED

# Frozen for seed 20260927. A change here means the RNG or the weight table moved, which is a
# balance change and must be a deliberate edit, not a surprise.
FROZEN_INTERVALS = [
    186.219923,
    249.986733,
    260.504059,
    137.423082,
    281.261543,
    234.660537,
    245.112349,
    185.907052,
    185.491238,
    264.052754,
    191.858323,
    241.216601,
    263.883369,
    226.002906,
    120.577771,
    263.377044,
    185.546396,
    209.907544,
    162.613353,
    255.664925,
]
FROZEN_EFFECTS = [
    "gold_click_frenzy",
    "gold_frenzy",
    "gold_frenzy",
    "gold_lucky",
    "gold_lucky",
    "gold_lucky",
    "gold_lucky",
    "gold_click_frenzy",
    "gold_lucky",
    "gold_lucky",
    "gold_lucky",
    "gold_blessing",
    "gold_frenzy",
    "gold_lucky",
    "gold_windfall",
    "gold_lucky",
    "gold_lucky",
    "gold_blessing",
    "gold_blessing",
    "gold_frenzy",
]


def phase_of(state: GameState) -> GoldenPhase:
    """Read the phase through a call so a previous assertion cannot narrow the type away."""
    return state.golden_phase


def test_frozen_spawn_intervals(state: GameState) -> None:
    span = GOLDEN_INTERVAL_MAX - GOLDEN_INTERVAL_MIN
    for counter, expected in enumerate(FROZEN_INTERVALS):
        unit = rng.unit(state.rng_seed, rng.STREAM_GOLDEN_SPAWN, counter)
        assert GOLDEN_INTERVAL_MIN + unit * span == pytest.approx(expected, abs=1e-6)


def test_frozen_effect_sequence(state: GameState, content: ContentIndex) -> None:
    drawn = []
    for _ in FROZEN_EFFECTS:
        drawn.append(golden.draw_effect(state, content).id)
    assert drawn == FROZEN_EFFECTS


def test_a_new_game_schedules_the_first_spawn_inside_the_window(state: GameState) -> None:
    assert GOLDEN_INTERVAL_MIN <= state.golden_next_spawn_at < GOLDEN_INTERVAL_MAX
    assert phase_of(state) is GoldenPhase.IDLE
    assert state.golden_spawn_counter == 1


def test_idle_becomes_visible_at_the_scheduled_time(
    state: GameState, content: ContentIndex
) -> None:
    state.golden_next_spawn_at = 1.0
    result = advance(state, 0.9, content=content)
    assert not result.golden_spawned
    assert phase_of(state) is GoldenPhase.IDLE

    result = advance(state, 0.2, content=content)
    assert result.golden_spawned
    assert phase_of(state) is GoldenPhase.VISIBLE
    assert state.golden_visible_until == pytest.approx(state.time_played + GOLDEN_LIFETIME, abs=0.2)


def test_an_uncaught_cookie_expires_and_counts_as_missed(
    state: GameState, content: ContentIndex
) -> None:
    state.golden_next_spawn_at = 0.5
    advance(state, 1.0, content=content)
    assert phase_of(state) is GoldenPhase.VISIBLE

    result = advance(state, GOLDEN_LIFETIME + 0.5, content=content)
    assert result.golden_expired
    assert state.golden_cookies_missed == 1
    assert state.golden_cookies_caught == 0
    assert phase_of(state) is GoldenPhase.IDLE
    assert state.golden_next_spawn_at > state.time_played


def test_catching_applies_an_effect_and_reschedules(
    state: GameState, content: ContentIndex
) -> None:
    state.owned = {"grandma": 100}
    state.cookies = 1_000_000.0
    state.golden_next_spawn_at = 0.1
    state.revision += 1
    advance(state, 0.3, content=content)
    assert phase_of(state) is GoldenPhase.VISIBLE

    caught = catch_golden(state, content)
    assert caught is not None
    assert caught.effect_id in {spec.id for spec in CONTENT.golden_effects}
    assert state.golden_cookies_caught == 1
    assert state.golden_cookies_missed == 0
    assert phase_of(state) is GoldenPhase.IDLE


def test_catching_nothing_is_not_an_error(state: GameState, content: ContentIndex) -> None:
    assert phase_of(state) is GoldenPhase.IDLE
    assert catch_golden(state, content) is None
    assert state.golden_cookies_caught == 0


def test_a_miss_does_not_consume_an_effect_roll(state: GameState, content: ContentIndex) -> None:
    """The two streams are independent so that catch behaviour cannot shift spawn timing."""
    state.golden_next_spawn_at = 0.1
    advance(state, 0.2, content=content)
    advance(state, GOLDEN_LIFETIME + 0.2, content=content)
    assert state.golden_cookies_missed == 1
    assert state.golden_effect_counter == 0
    assert state.golden_spawn_counter == 2


def test_an_instant_effect_credits_cookies_and_stores_nothing(
    state: GameState, content: ContentIndex
) -> None:
    lucky = CONTENT.achievement_by_id  # touch the index so a typo in the fixture is caught early
    assert lucky is not None
    spec = next(s for s in CONTENT.golden_effects if s.id == "gold_lucky")
    state.owned = {"grandma": 100}
    state.cookies = 10_000.0
    state.revision += 1
    before = state.cookies

    lump = golden.apply_effect(state, spec, content)
    expected = min(0.10 * before, 300.0 * derive(state, content).cps_without_events()) + 13.0
    assert lump == pytest.approx(expected)
    assert state.cookies == pytest.approx(before + lump)
    assert state.cookies_from_golden == pytest.approx(lump)
    assert state.active_effects == []


def test_a_timed_effect_replaces_the_one_in_its_slot(
    state: GameState, content: ContentIndex
) -> None:
    frenzy = next(s for s in CONTENT.golden_effects if s.id == "gold_frenzy")
    blessing = next(s for s in CONTENT.golden_effects if s.id == "gold_blessing")

    golden.apply_effect(state, frenzy, content)
    golden.apply_effect(state, blessing, content)
    assert len(state.active_effects) == 1
    assert state.active_effects[0].effect_id == "gold_blessing"

    click = next(s for s in CONTENT.golden_effects if s.slot is EffectSlot.CLICK_MULT)
    golden.apply_effect(state, click, content)
    slots = sorted(effect.slot for effect in state.active_effects)
    assert slots == sorted([EffectSlot.CPS_MULT, EffectSlot.CLICK_MULT])


def test_effects_survive_until_their_duration_and_then_expire(
    state: GameState, content: ContentIndex
) -> None:
    """A one-second effect lasts exactly one second, split across two advance calls."""
    state.active_effects = [ActiveEffect("gold_frenzy", EffectSlot.CPS_MULT, 7.0, 1.0)]
    state.revision += 1

    result = advance(state, 0.5, content=content)
    assert result.effects_expired == []
    assert state.active_effects

    result = advance(state, 0.5, content=content)
    assert result.effects_expired == ["gold_frenzy"]
    assert state.active_effects == []


def test_a_partial_tick_does_not_expire_an_effect_early(
    state: GameState, content: ContentIndex
) -> None:
    state.active_effects = [ActiveEffect("gold_frenzy", EffectSlot.CPS_MULT, 7.0, 1.0)]
    state.revision += 1
    for _ in range(9):
        assert advance(state, FIXED_DT, content=content).effects_expired == []
    assert advance(state, FIXED_DT, content=content).effects_expired == ["gold_frenzy"]


def test_the_lure_upgrades_shorten_the_scheduled_interval(
    state: GameState, content: ContentIndex
) -> None:
    state.upgrades_owned = {"up_golden_lure", "up_golden_beacon"}
    state.revision += 1
    counter = state.golden_spawn_counter
    golden.reschedule(state, content)
    expected = FROZEN_INTERVALS[counter] * 0.68
    assert state.golden_next_spawn_at == pytest.approx(expected, abs=1e-5)


def test_seed_determines_the_sequence() -> None:
    first = new_game(seed=SEED, now=0.0)
    second = new_game(seed=SEED, now=0.0)
    other = new_game(seed=SEED + 1, now=0.0)
    assert first.golden_next_spawn_at == second.golden_next_spawn_at
    assert first.golden_next_spawn_at != other.golden_next_spawn_at
