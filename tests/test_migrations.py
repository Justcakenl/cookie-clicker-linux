"""The migration chain, proven before a real migration exists.

The table ships empty, so these tests inject a synthetic one. That is deliberate: the day the first
real migration is written, the loop, the missing-step branch, and the future-version branch are
already known to work, and the only new thing to get right is the transformation itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cookie.engine.content import ContentIndex
from cookie.engine.state import GameState
from cookie.persistence.codec import decode
from cookie.persistence.migrations import (
    MIGRATIONS,
    SAVE_VERSION,
    FutureSaveVersionError,
    MissingMigrationError,
    migrate,
)
from cookie.persistence.store import LoadStatus, SaveStore
from tests.conftest import EPOCH

FIXTURES = Path(__file__).parent / "fixtures"


def test_the_shipped_table_is_empty_at_version_one() -> None:
    """A non-empty table at SAVE_VERSION 1 would mean a version was released without a bump."""
    assert SAVE_VERSION == 1
    assert dict(MIGRATIONS) == {}


def test_a_current_payload_passes_through_untouched() -> None:
    payload: dict[str, Any] = {"state": {"cookies": 1.0}, "settings": {}}
    migrated, notes = migrate(payload, SAVE_VERSION)
    assert migrated is payload
    assert notes == []


def test_the_chain_runs_every_step_in_order() -> None:
    def add_one(payload: dict[str, Any]) -> dict[str, Any]:
        return {**payload, "steps": [*payload.get("steps", []), "0->1"]}

    def add_two(payload: dict[str, Any]) -> dict[str, Any]:
        return {**payload, "steps": [*payload.get("steps", []), "1->2"]}

    table = {-1: add_one, 0: add_two}
    migrated, notes = migrate({}, -1, migrations=table)
    assert migrated["steps"] == ["0->1", "1->2"]
    assert notes == [
        "migrated save from v-1 to v0",
        "migrated save from v0 to v1",
    ]


def test_a_gap_in_the_chain_is_an_error() -> None:
    with pytest.raises(MissingMigrationError) as caught:
        migrate({}, 0, migrations={})
    assert caught.value.version == 0


def test_a_future_version_is_an_error() -> None:
    with pytest.raises(FutureSaveVersionError) as caught:
        migrate({}, SAVE_VERSION + 5)
    assert caught.value.version == SAVE_VERSION + 5


def test_a_frozen_older_payload_upgrades_and_decodes(content: ContentIndex) -> None:
    """A stored v0 sample, carried forward by a synthetic step, must produce a usable state.

    This is the shape every future migration is tested in: a payload written by an older version,
    the chain, and then a real decode.
    """
    old = json.loads((FIXTURES / "save_v0.json").read_text(encoding="utf-8"))

    def v0_to_v1(payload: dict[str, Any]) -> dict[str, Any]:
        state = dict(payload["state"])
        # v0 had no run_cookies and tracked nothing about golden cookies.
        state["run_cookies"] = state["all_time_cookies"]
        state["golden_phase"] = "idle"
        state["golden_next_spawn_at"] = 180.0
        state["golden_visible_until"] = 0.0
        state["golden_spawn_counter"] = 1
        state["golden_effect_counter"] = 0
        state["active_effects"] = []
        state["golden_cookies_caught"] = 0
        state["golden_cookies_missed"] = 0
        state["cookies_from_clicks"] = 0.0
        state["cookies_from_offline"] = 0.0
        state["cookies_from_golden"] = 0.0
        state["max_cps_seen"] = 0.0
        state["buildings_bought_total"] = 0
        state["revealed_buildings"] = ["cursor"]
        state["tick_accumulator"] = 0.0
        state["next_unlock_scan_at"] = 1.0
        state["revision"] = 0
        return {"state": state, "settings": payload.get("settings", {})}

    migrated, notes = migrate(old["payload"], old["version"], migrations={0: v0_to_v1})
    assert notes == ["migrated save from v0 to v1"]

    state, decode_notes = decode(migrated, saved_at=EPOCH, content=content)
    assert state.all_time_cookies == 123_456.0
    assert state.run_cookies == 123_456.0
    assert state.owned == {"cursor": 12, "grandma": 4}
    assert state.total_clicks == 250
    assert decode_notes == []


def test_the_loader_refuses_a_version_it_cannot_migrate(
    tmp_path: Path, content: ContentIndex, state: GameState
) -> None:
    """Without a real step for v0, the shipped loader must reject rather than guess."""
    store = SaveStore(tmp_path / "cookie", content=content)
    envelope = store.build_envelope(state, now=EPOCH)
    envelope["version"] = 0
    store.save_path.parent.mkdir(parents=True, exist_ok=True)
    store.save_path.write_text(json.dumps(envelope), encoding="utf-8")

    result = store.load(now=EPOCH)
    assert result.status is LoadStatus.CORRUPT_STARTED_FRESH
    assert any("migration failed" in note for note in result.notes)
