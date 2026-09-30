"""Given the same seed and the same deltas, the engine must land on the same state."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from cookie.engine import derive as derive_module
from cookie.engine.actions import buy_building, catch_golden, click
from cookie.engine.content import ContentIndex
from cookie.engine.state import GameState, GoldenPhase, new_game
from cookie.engine.tick import advance
from tests.conftest import SEED

DELTA_SCRIPT: Sequence[float] = (
    0.1,
    0.1,
    0.05,
    0.35,
    1.0,
    0.1,
    2.5,
    0.1,
    0.1,
    13.0,
    0.4,
    7.0,
    0.1,
    61.0,
    0.2,
    120.0,
    0.1,
)


def _snapshot(state: GameState) -> dict[str, object]:
    """Every persisted field, rendered so that floats compare exactly."""
    fields: dict[str, object] = {}
    for name in GameState.__slots__:
        if name == "settings":
            continue
        value = getattr(state, name)
        if name == "active_effects":
            fields[name] = [
                (effect.effect_id, effect.slot, repr(effect.magnitude), repr(effect.remaining))
                for effect in value
            ]
        elif isinstance(value, set):
            fields[name] = sorted(value)
        elif isinstance(value, dict):
            fields[name] = sorted(value.items())
        else:
            fields[name] = repr(value)
    return fields


def _run(content: ContentIndex, *, seed: int = SEED) -> GameState:
    derive_module.invalidate_cache()
    state = new_game(seed=seed, now=0.0)
    for index, delta in enumerate(DELTA_SCRIPT):
        advance(state, delta, content=content)
        if index % 3 == 0:
            click(state, content)
        if state.golden_phase is GoldenPhase.VISIBLE:
            catch_golden(state, content)
        if state.cookies >= 15.0:
            buy_building(state, content, "cursor", 1)
    return state


def test_the_same_script_produces_the_same_state(content: ContentIndex) -> None:
    assert _snapshot(_run(content)) == _snapshot(_run(content))


def test_a_different_seed_produces_a_different_schedule(content: ContentIndex) -> None:
    first = _run(content)
    other = _run(content, seed=SEED + 1)
    assert first.golden_next_spawn_at != other.golden_next_spawn_at


def test_splitting_a_delta_does_not_change_the_outcome(content: ContentIndex) -> None:
    """The accumulator carries the remainder, so frame rate must not affect earnings."""
    derive_module.invalidate_cache()
    coarse = new_game(seed=SEED, now=0.0)
    coarse.owned = {"grandma": 7}
    coarse.revision += 1
    advance(coarse, 3.0, content=content)

    derive_module.invalidate_cache()
    fine = new_game(seed=SEED, now=0.0)
    fine.owned = {"grandma": 7}
    fine.revision += 1
    for _ in range(60):
        advance(fine, 0.05, content=content)

    assert fine.cookies == pytest.approx(coarse.cookies)
    assert fine.time_played == pytest.approx(coarse.time_played)
    assert fine.golden_phase is coarse.golden_phase


def test_the_rng_counter_is_the_whole_stream_state(content: ContentIndex) -> None:
    """Reconstructing a state from its fields must continue the same sequence."""
    original = _run(content)

    derive_module.invalidate_cache()
    copy = new_game(seed=original.rng_seed, now=0.0)
    for name in GameState.__slots__:
        if name == "settings":
            continue
        setattr(copy, name, getattr(original, name))

    advance(original, 200.0, content=content)
    advance(copy, 200.0, content=content)
    assert _snapshot(original) == _snapshot(copy)
