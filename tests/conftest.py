"""Shared fixtures. The engine takes time as an argument, so no test ever sleeps."""

from __future__ import annotations

import pytest

from cookie.engine import derive
from cookie.engine.content import CONTENT, ContentIndex
from cookie.engine.state import GameState, new_game

SEED = 20260927
EPOCH = 1_774_000_000.0


@pytest.fixture
def content() -> ContentIndex:
    return CONTENT


@pytest.fixture
def state() -> GameState:
    """A fresh game at a fixed seed. The derive cache is cleared so tests cannot leak into it."""
    derive.invalidate_cache()
    return new_game(seed=SEED, now=EPOCH)
