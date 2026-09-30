"""Round trip, atomicity, and backup rotation."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from cookie.engine.actions import buy_building, click
from cookie.engine.content import ContentIndex
from cookie.engine.specs import EffectSlot
from cookie.engine.state import ActiveEffect, GameState
from cookie.engine.tick import advance
from cookie.persistence import paths
from cookie.persistence.codec import encode, payload_checksum
from cookie.persistence.store import LoadStatus, SaveError, SaveStore
from tests.conftest import EPOCH


@pytest.fixture
def store(tmp_path: Path, content: ContentIndex) -> SaveStore:
    return SaveStore(tmp_path / "cookie", content=content, app_version="1.0.0")


def _played(state: GameState, content: ContentIndex) -> GameState:
    """A state with something interesting in every field group."""
    state.cookies = 12_345.678
    state.owned = {"cursor": 23, "grandma": 14}
    state.upgrades_owned = {"up_cursor_1", "up_grandma_1"}
    state.achievements_unlocked = {"ach_clicks_10", "ach_first_cursor"}
    state.revealed_buildings = {"cursor", "grandma", "farm"}
    state.heavenly_chips = 3
    state.prestige_count = 1
    state.active_effects = [ActiveEffect("gold_frenzy", EffectSlot.CPS_MULT, 7.0, 12.5)]
    state.total_clicks = 361
    state.golden_cookies_caught = 4
    state.golden_cookies_missed = 2
    state.cookies_from_clicks = 361.0
    state.cookies_from_golden = 88.0
    state.cookies_from_offline = 4_000.0
    state.max_cps_seen = 412.5
    state.buildings_bought_total = 37
    state.revision += 1
    advance(state, 3.0, content=content)
    return state


def test_round_trip_preserves_every_field(
    store: SaveStore, state: GameState, content: ContentIndex
) -> None:
    original = _played(state, content)
    store.save(original, now=EPOCH)

    result = store.load()
    assert result.status is LoadStatus.OK
    assert result.source == store.save_path
    loaded = result.state

    for name in GameState.__slots__:
        if name in {"settings", "last_saved_at", "active_effects"}:
            continue
        assert getattr(loaded, name) == getattr(original, name), name
    assert loaded.last_saved_at == EPOCH
    assert [
        (effect.effect_id, effect.slot, effect.magnitude, effect.remaining)
        for effect in loaded.active_effects
    ] == [
        (effect.effect_id, effect.slot, effect.magnitude, effect.remaining)
        for effect in original.active_effects
    ]


def test_settings_round_trip(store: SaveStore, state: GameState) -> None:
    state.settings.number_format = "scientific"
    state.settings.animations = False
    state.settings.theme = "high_contrast"
    state.settings.confirm_purchases = True
    state.settings.show_flavor = False
    store.save(state, now=EPOCH)

    loaded = store.load().state.settings
    assert loaded.number_format == "scientific"
    assert loaded.animations is False
    assert loaded.theme == "high_contrast"
    assert loaded.confirm_purchases is True
    assert loaded.show_flavor is False


def test_sets_are_serialised_sorted_so_saves_are_reproducible(
    store: SaveStore, state: GameState, content: ContentIndex
) -> None:
    """Byte-stable saves mean a diff between two files is a real difference in the game."""
    _played(state, content)
    state.upgrades_owned = {"up_grandma_1", "up_cursor_1", "up_cursor_5"}
    state.achievements_unlocked = {"ach_first_cursor", "ach_clicks_10"}

    payload = store.build_envelope(state, now=EPOCH)["payload"]
    assert payload["state"]["upgrades_owned"] == [
        "up_cursor_1",
        "up_cursor_5",
        "up_grandma_1",
    ]
    assert payload["state"]["achievements_unlocked"] == ["ach_clicks_10", "ach_first_cursor"]
    assert payload["state"]["revealed_buildings"] == sorted(state.revealed_buildings)
    assert list(payload["state"]["owned"]) == sorted(state.owned)

    first = json.dumps(store.build_envelope(state, now=EPOCH), sort_keys=True)
    second = json.dumps(store.build_envelope(state, now=EPOCH), sort_keys=True)
    assert first == second


def test_an_empty_directory_is_a_new_game(store: SaveStore) -> None:
    result = store.load()
    assert result.status is LoadStatus.NEW_GAME
    assert result.source is None
    assert result.notes == ()
    assert not result.needs_acknowledgement
    assert result.state.all_time_cookies == 0.0


def test_the_save_directory_and_file_are_private(store: SaveStore, state: GameState) -> None:
    store.save(state, now=EPOCH)
    assert store.save_path.exists()
    assert store.save_path.stat().st_mode & 0o777 == paths.FILE_MODE
    assert store.directory.stat().st_mode & 0o777 == paths.DIR_MODE


def test_no_temp_file_is_left_behind(store: SaveStore, state: GameState) -> None:
    store.save(state, now=EPOCH)
    leftovers = list(store.directory.glob("*.tmp.*"))
    assert leftovers == []


def test_saving_records_the_timestamp_on_the_state(store: SaveStore, state: GameState) -> None:
    store.save(state, now=EPOCH)
    assert state.last_saved_at == EPOCH


def test_rotation_keeps_exactly_three_generations(store: SaveStore, state: GameState) -> None:
    for generation in range(6):
        state.all_time_cookies = float(generation)
        state.run_cookies = float(generation)
        state.revision += 1
        store.save(state, now=EPOCH + generation)

    backups = paths.backup_paths(store.directory)
    assert all(path.exists() for path in backups)
    assert len(list(store.directory.glob("save.json.bak.*"))) == 3

    # The newest backup is the generation before last, and they descend from there.
    def total(path: Path) -> float:
        envelope = json.loads(path.read_bytes())
        return float(envelope["payload"]["state"]["all_time_cookies"])

    assert total(store.save_path) == 5.0
    assert [total(path) for path in backups] == [4.0, 3.0, 2.0]


def test_the_first_save_creates_no_backup(store: SaveStore, state: GameState) -> None:
    store.save(state, now=EPOCH)
    assert list(store.directory.glob("save.json.bak.*")) == []


def test_a_failed_publish_leaves_the_previous_save_loadable(
    store: SaveStore, state: GameState, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rename is the only destructive step, so a crash there must cost nothing."""
    state.all_time_cookies = 100.0
    state.run_cookies = 100.0
    store.save(state, now=EPOCH)

    def refuse(self: Path, target: str | os.PathLike[str]) -> Path:
        raise OSError(5, "simulated I/O error")

    state.all_time_cookies = 999.0
    state.run_cookies = 999.0
    state.revision += 1
    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(SaveError):
        store.save(state, now=EPOCH + 1)
    monkeypatch.undo()

    result = store.load()
    assert result.status is LoadStatus.OK
    assert result.state.all_time_cookies == 100.0
    assert list(store.directory.glob("*.tmp.*")) == []


def test_a_nan_in_state_fails_at_save_time_and_keeps_the_old_file(
    store: SaveStore, state: GameState
) -> None:
    """Loud at write, with the previous save intact, beats a file that will not parse back."""
    state.all_time_cookies = 500.0
    state.run_cookies = 500.0
    store.save(state, now=EPOCH)

    state.cookies = math.nan
    state.revision += 1
    with pytest.raises(ValueError, match=r"Out of range float|not JSON compliant|nan"):
        store.save(state, now=EPOCH + 1)

    assert store.load().state.all_time_cookies == 500.0


def test_the_checksum_covers_the_payload(state: GameState, content: ContentIndex) -> None:
    payload = encode(_played(state, content))
    original = payload_checksum(payload)
    payload["state"]["cookies"] = payload["state"]["cookies"] + 1.0
    assert payload_checksum(payload) != original


def test_clicking_and_buying_survive_a_round_trip(
    store: SaveStore, state: GameState, content: ContentIndex
) -> None:
    for _ in range(20):
        click(state, content)
    state.cookies = 1_000.0
    buy_building(state, content, "cursor", 5)
    advance(state, 10.0, content=content)
    store.save(state, now=EPOCH)

    loaded = store.load().state
    assert loaded.total_clicks == 20
    assert loaded.owned == {"cursor": 5}
    assert loaded.cookies == pytest.approx(state.cookies)
    assert loaded.achievements_unlocked == state.achievements_unlocked


def test_a_reloaded_state_continues_the_same_run(
    store: SaveStore, state: GameState, content: ContentIndex
) -> None:
    """The RNG counters are part of state, so continuing from disk is continuing the same stream."""
    state.owned = {"grandma": 10}
    state.revision += 1
    advance(state, 300.0, content=content)
    store.save(state, now=EPOCH)

    resumed = store.load().state
    advance(state, 120.0, content=content)
    advance(resumed, 120.0, content=content)
    assert resumed.golden_next_spawn_at == state.golden_next_spawn_at
    assert resumed.golden_spawn_counter == state.golden_spawn_counter
    assert resumed.cookies == pytest.approx(state.cookies)
