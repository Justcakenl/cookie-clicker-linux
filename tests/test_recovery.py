"""One test per branch of the recovery decision tree. Every file here is broken on purpose."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from cookie.engine.content import ContentIndex
from cookie.engine.state import GameState
from cookie.persistence import paths
from cookie.persistence.codec import DecodeError, payload_checksum
from cookie.persistence.store import LoadStatus, SaveStore
from tests.conftest import EPOCH

Mutator = Callable[[dict[str, Any]], None]


@pytest.fixture
def store(tmp_path: Path, content: ContentIndex) -> SaveStore:
    return SaveStore(tmp_path / "cookie", content=content, app_version="1.0.0")


def _write(path: Path, envelope: object, *, reseal: bool = False) -> None:
    if reseal and isinstance(envelope, dict) and isinstance(envelope.get("payload"), dict):
        envelope["checksum"] = payload_checksum(envelope["payload"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope), encoding="utf-8")


def _good_envelope(store: SaveStore, state: GameState, *, marker: float) -> dict[str, Any]:
    state.all_time_cookies = marker
    state.run_cookies = marker
    state.revision += 1
    return store.build_envelope(state, now=EPOCH)


def test_a_truncated_main_save_falls_back_to_a_backup(store: SaveStore, state: GameState) -> None:
    store.save(state, now=EPOCH)
    state.all_time_cookies = 777.0
    state.run_cookies = 777.0
    state.revision += 1
    store.save(state, now=EPOCH + 1)

    blob = store.save_path.read_text(encoding="utf-8")
    store.save_path.write_text(blob[: len(blob) // 2], encoding="utf-8")

    result = store.load()
    assert result.status is LoadStatus.RECOVERED_FROM_BACKUP
    assert result.source == paths.backup_paths(store.directory)[0]
    assert result.needs_acknowledgement
    assert result.state.all_time_cookies == 0.0
    assert any("not valid JSON" in note for note in result.notes)
    assert any("recovered from" in note for note in result.notes)


def test_a_single_flipped_byte_is_caught_by_the_checksum(
    store: SaveStore, state: GameState
) -> None:
    store.save(state, now=EPOCH)
    _write(paths.backup_paths(store.directory)[0], _good_envelope(store, state, marker=42.0))

    envelope = json.loads(store.save_path.read_text(encoding="utf-8"))
    envelope["payload"]["state"]["cookies"] = 1e12
    _write(store.save_path, envelope)

    result = store.load()
    assert result.status is LoadStatus.RECOVERED_FROM_BACKUP
    assert result.state.all_time_cookies == 42.0
    assert any("checksum mismatch" in note for note in result.notes)


def test_every_envelope_rejection_falls_through(store: SaveStore, state: GameState) -> None:
    cases: dict[str, Mutator] = {
        "not a cookie-save file": lambda env: env.__setitem__("format", "something-else"),
        "envelope is missing": lambda env: env.pop("checksum"),
        "payload is not an object": lambda env: env.__setitem__("payload", "nope"),
        "version is not an integer": lambda env: env.__setitem__("version", "1"),
        "saved_at is not a timestamp": lambda env: env.__setitem__("saved_at", "yesterday"),
    }
    for expected, mutate in cases.items():
        envelope = _good_envelope(store, state, marker=1.0)
        mutate(envelope)
        _write(store.save_path, envelope)
        result = store.load()
        assert result.status is LoadStatus.CORRUPT_STARTED_FRESH, expected
        assert any(expected in note for note in result.notes), (expected, result.notes)
        for leftover in store.directory.glob("save.json.corrupt.*"):
            leftover.unlink()


def test_a_top_level_list_is_rejected(store: SaveStore) -> None:
    _write(store.save_path, [1, 2, 3])
    result = store.load()
    assert result.status is LoadStatus.CORRUPT_STARTED_FRESH
    assert any("top level is not an object" in note for note in result.notes)


def test_a_save_from_the_future_is_refused_rather_than_guessed_at(
    store: SaveStore, state: GameState
) -> None:
    envelope = _good_envelope(store, state, marker=5.0)
    envelope["version"] = 99
    _write(store.save_path, envelope)

    result = store.load()
    assert result.status is LoadStatus.CORRUPT_STARTED_FRESH
    assert any("newer version of the game" in note for note in result.notes)


def test_every_decode_rejection_falls_through(store: SaveStore, state: GameState) -> None:
    cases: dict[str, Mutator] = {
        "missing field: cookies": lambda env: env["payload"]["state"].pop("cookies"),
        "must not be negative": lambda env: env["payload"]["state"].__setitem__("total_clicks", -1),
        "must be at least 0.0": lambda env: env["payload"]["state"].__setitem__("cookies", -5.0),
        "below run_cookies": lambda env: env["payload"]["state"].__setitem__("run_cookies", 1e30),
        "unknown golden phase": lambda env: env["payload"]["state"].__setitem__(
            "golden_phase", "dancing"
        ),
        "unknown number format": lambda env: env["payload"]["settings"].__setitem__(
            "number_format", "roman"
        ),
        "owned[cursor] must be an integer": lambda env: env["payload"]["state"].__setitem__(
            "owned", {"cursor": "many"}
        ),
        "owned must be an object": lambda env: env["payload"]["state"].__setitem__(
            "owned", ["cursor"]
        ),
    }
    for expected, mutate in cases.items():
        envelope = _good_envelope(store, state, marker=1.0)
        mutate(envelope)
        _write(store.save_path, envelope, reseal=True)
        result = store.load()
        assert result.status is LoadStatus.CORRUPT_STARTED_FRESH, expected
        assert any(expected in note for note in result.notes), (expected, result.notes)
        for leftover in store.directory.glob("save.json.corrupt.*"):
            leftover.unlink()


def test_a_non_finite_value_cannot_even_be_hashed(store: SaveStore, state: GameState) -> None:
    """json.loads accepts Infinity, so the checksum is the gate that keeps it out of state."""
    envelope = _good_envelope(store, state, marker=1.0)
    envelope["payload"]["state"]["cookies"] = float("inf")
    _write(store.save_path, envelope)

    result = store.load()
    assert result.status is LoadStatus.CORRUPT_STARTED_FRESH
    assert any("cannot be hashed" in note for note in result.notes)


def test_an_active_effect_must_be_a_timed_slot_with_time_left(
    store: SaveStore, state: GameState
) -> None:
    for effect, expected in (
        (
            {"effect_id": "x", "slot": "instant", "magnitude": 1.0, "remaining": 5.0},
            "cannot be an active effect",
        ),
        (
            {"effect_id": "x", "slot": "cps_mult", "magnitude": 7.0, "remaining": 0.0},
            "remaining must be positive",
        ),
        (
            {"effect_id": "x", "slot": "nonsense", "magnitude": 7.0, "remaining": 5.0},
            "unknown effect slot",
        ),
    ):
        envelope = _good_envelope(store, state, marker=1.0)
        envelope["payload"]["state"]["active_effects"] = [effect]
        _write(store.save_path, envelope, reseal=True)
        result = store.load()
        assert result.status is LoadStatus.CORRUPT_STARTED_FRESH
        assert any(expected in note for note in result.notes), (expected, result.notes)
        for leftover in store.directory.glob("save.json.corrupt.*"):
            leftover.unlink()


def test_two_effects_in_one_slot_are_rejected(store: SaveStore, state: GameState) -> None:
    envelope = _good_envelope(store, state, marker=1.0)
    envelope["payload"]["state"]["active_effects"] = [
        {"effect_id": "a", "slot": "cps_mult", "magnitude": 7.0, "remaining": 5.0},
        {"effect_id": "b", "slot": "cps_mult", "magnitude": 1.5, "remaining": 5.0},
    ]
    _write(store.save_path, envelope, reseal=True)
    result = store.load()
    assert result.status is LoadStatus.CORRUPT_STARTED_FRESH
    assert any("share slot" in note for note in result.notes)


def test_a_damaged_save_is_kept_not_deleted(store: SaveStore) -> None:
    store.save_path.parent.mkdir(parents=True, exist_ok=True)
    store.save_path.write_text("this is not a save", encoding="utf-8")

    result = store.load(now=EPOCH)
    assert result.status is LoadStatus.CORRUPT_STARTED_FRESH
    assert result.needs_acknowledgement
    quarantined = list(store.directory.glob("save.json.corrupt.*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "this is not a save"
    assert any(str(quarantined[0]) in note for note in result.notes)
    assert not store.save_path.exists()


def test_all_four_candidates_broken_starts_fresh(store: SaveStore) -> None:
    for candidate in paths.load_candidates(store.directory):
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text("{", encoding="utf-8")

    result = store.load(now=EPOCH)
    assert result.status is LoadStatus.CORRUPT_STARTED_FRESH
    assert result.state.all_time_cookies == 0.0
    assert len([note for note in result.notes if "not valid JSON" in note]) == 4


def test_the_third_backup_is_used_when_everything_newer_is_broken(
    store: SaveStore, state: GameState
) -> None:
    good = _good_envelope(store, state, marker=31.0)
    _write(paths.backup_paths(store.directory)[2], good)
    for candidate in paths.load_candidates(store.directory)[:3]:
        candidate.write_text("broken", encoding="utf-8")

    result = store.load()
    assert result.status is LoadStatus.RECOVERED_FROM_BACKUP
    assert result.source == paths.backup_paths(store.directory)[2]
    assert result.state.all_time_cookies == 31.0


def test_unknown_ids_are_dropped_rather_than_bricking_the_save(
    store: SaveStore, state: GameState
) -> None:
    """Shrinking content in a future version must not make an old save unloadable."""
    envelope = _good_envelope(store, state, marker=1.0)
    envelope["payload"]["state"]["owned"]["obsolete_building"] = 5
    envelope["payload"]["state"]["upgrades_owned"] = ["up_cursor_1", "up_removed"]
    envelope["payload"]["state"]["achievements_unlocked"] = ["ach_gone"]
    envelope["payload"]["state"]["revealed_buildings"] = ["cursor", "atlantis"]
    _write(store.save_path, envelope, reseal=True)

    result = store.load()
    assert result.status is LoadStatus.OK
    assert result.state.owned == {}
    assert result.state.upgrades_owned == {"up_cursor_1"}
    assert result.state.achievements_unlocked == set()
    assert result.state.revealed_buildings == {"cursor"}
    assert any("no longer knows" in note for note in result.notes)


def test_an_empty_revealed_set_is_repaired(store: SaveStore, state: GameState) -> None:
    """The first building is always revealed; an empty set would hide the whole shop."""
    envelope = _good_envelope(store, state, marker=1.0)
    envelope["payload"]["state"]["revealed_buildings"] = []
    _write(store.save_path, envelope, reseal=True)

    result = store.load()
    assert result.status is LoadStatus.OK
    assert result.state.revealed_buildings == {"cursor"}
    assert any("restored the first building" in note for note in result.notes)


def test_import_adopts_a_file_and_keeps_the_replaced_save(
    store: SaveStore, state: GameState, tmp_path: Path
) -> None:
    state.all_time_cookies = 10.0
    state.run_cookies = 10.0
    store.save(state, now=EPOCH)

    external = tmp_path / "elsewhere.json"
    _write(external, _good_envelope(store, state, marker=5_000.0))

    result = store.import_from(external, now=EPOCH + 1)
    assert result.state.all_time_cookies == 5_000.0
    assert store.load().state.all_time_cookies == 5_000.0

    previous = json.loads(paths.backup_paths(store.directory)[0].read_bytes())
    assert previous["payload"]["state"]["all_time_cookies"] == 10.0


def test_a_bad_import_changes_nothing(store: SaveStore, state: GameState, tmp_path: Path) -> None:
    state.all_time_cookies = 10.0
    state.run_cookies = 10.0
    store.save(state, now=EPOCH)

    external = tmp_path / "junk.json"
    external.write_text("not a save at all", encoding="utf-8")
    with pytest.raises(DecodeError, match="cannot import"):
        store.import_from(external)

    assert store.load().state.all_time_cookies == 10.0


def test_export_then_import_round_trips(
    store: SaveStore, state: GameState, content: ContentIndex, tmp_path: Path
) -> None:
    state.all_time_cookies = 4_242.0
    state.run_cookies = 4_242.0
    state.owned = {"grandma": 7}
    state.revision += 1

    destination = tmp_path / "export" / paths.export_name(now=EPOCH)
    store.export_to(destination, state)
    assert destination.exists()

    result = store.import_from(destination)
    assert result.state.all_time_cookies == 4_242.0
    assert result.state.owned == {"grandma": 7}
