"""The CPS and click formulas, term by term, per docs/ARCHITECTURE.md §5.1."""

from __future__ import annotations

import dataclasses

import pytest

from cookie.engine import derive as derive_module
from cookie.engine.content import ContentIndex
from cookie.engine.derive import derive
from cookie.engine.specs import EffectSlot
from cookie.engine.state import ActiveEffect, GameState


def test_an_empty_game_produces_nothing_and_clicks_for_one(
    state: GameState, content: ContentIndex
) -> None:
    snapshot = derive(state, content)
    assert snapshot.base_cps == 0.0
    assert snapshot.cps == 0.0
    assert snapshot.click_value == 1.0
    assert snapshot.global_upgrade_mult == 1.0
    assert snapshot.achievement_mult == 1.0
    assert snapshot.prestige_mult == 1.0
    assert snapshot.event_mult == 1.0
    assert snapshot.golden_interval_mult == 1.0


def test_base_cps_is_the_sum_over_owned_buildings(state: GameState, content: ContentIndex) -> None:
    state.owned = {"cursor": 10, "grandma": 3}
    state.revision += 1
    snapshot = derive(state, content)
    assert snapshot.base_cps == pytest.approx(10 * 0.1 + 3 * 1.0)
    assert snapshot.building_cps["cursor"] == pytest.approx(1.0)
    assert snapshot.building_cps["grandma"] == pytest.approx(3.0)
    assert snapshot.building_cps["farm"] == 0.0


def test_a_building_multiplier_scales_only_its_own_building(
    state: GameState, content: ContentIndex
) -> None:
    state.owned = {"cursor": 10, "grandma": 10}
    state.upgrades_owned = {"up_cursor_1"}
    state.revision += 1
    snapshot = derive(state, content)
    assert snapshot.building_mult["cursor"] == 2.0
    assert snapshot.building_mult["grandma"] == 1.0
    assert snapshot.building_cps["cursor"] == pytest.approx(2.0)
    assert snapshot.building_cps["grandma"] == pytest.approx(10.0)
    assert snapshot.base_cps == pytest.approx(12.0)


def test_building_multipliers_stack_multiplicatively(
    state: GameState, content: ContentIndex
) -> None:
    state.owned = {"cursor": 100}
    state.upgrades_owned = {f"up_cursor_{m}" for m in (1, 5, 25, 50, 100)}
    state.revision += 1
    snapshot = derive(state, content)
    assert snapshot.building_mult["cursor"] == 32.0
    assert snapshot.base_cps == pytest.approx(100 * 0.1 * 32.0)


def test_global_achievement_and_prestige_multipliers_apply_to_the_summed_base(
    state: GameState, content: ContentIndex
) -> None:
    state.owned = {"grandma": 10}
    state.upgrades_owned = {"up_global_variety"}
    state.achievements_unlocked = {"ach_clicks_10", "ach_clicks_100"}
    state.heavenly_chips = 4
    state.revision += 1
    snapshot = derive(state, content)
    assert snapshot.global_upgrade_mult == pytest.approx(1.05)
    assert snapshot.achievement_mult == pytest.approx(1.02)
    assert snapshot.prestige_mult == pytest.approx(1.20)
    assert snapshot.cps == pytest.approx(10.0 * 1.05 * 1.02 * 1.20)


def test_a_cps_event_multiplies_cps_and_is_removable(
    state: GameState, content: ContentIndex
) -> None:
    state.owned = {"grandma": 10}
    state.active_effects = [ActiveEffect("gold_frenzy", EffectSlot.CPS_MULT, 7.0, 30.0)]
    state.revision += 1
    snapshot = derive(state, content)
    assert snapshot.event_mult == 7.0
    assert snapshot.cps == pytest.approx(70.0)
    assert snapshot.cps_without_events() == pytest.approx(10.0)


def test_click_value_combines_flat_multiplier_and_cps_share(
    state: GameState, content: ContentIndex
) -> None:
    state.owned = {"grandma": 100}
    state.upgrades_owned = {"up_click_thimble", "up_click_double", "up_click_share_1"}
    state.revision += 1
    snapshot = derive(state, content)
    assert snapshot.click_flat_bonus == 1.0
    assert snapshot.click_multiplier == 2.0
    assert snapshot.click_cps_share == 0.01
    # (1 + 1) * 2, then the share of a 100 CPS bakery.
    assert snapshot.click_value == pytest.approx(4.0 + 1.0)


def test_the_cps_share_term_ignores_a_frenzy(state: GameState, content: ContentIndex) -> None:
    """Otherwise a Frenzy and a Click Frenzy would compound into an unbudgeted multiplier."""
    state.owned = {"grandma": 100}
    state.upgrades_owned = {"up_click_share_1"}
    state.revision += 1
    without = derive(state, content).click_value

    state.active_effects = [ActiveEffect("gold_frenzy", EffectSlot.CPS_MULT, 7.0, 30.0)]
    state.revision += 1
    with_frenzy = derive(state, content).click_value
    assert with_frenzy == pytest.approx(without)


def test_a_click_event_multiplies_only_the_click_term(
    state: GameState, content: ContentIndex
) -> None:
    state.owned = {"grandma": 100}
    state.upgrades_owned = {"up_click_share_1"}
    state.active_effects = [ActiveEffect("gold_click_frenzy", EffectSlot.CLICK_MULT, 777.0, 13.0)]
    state.revision += 1
    snapshot = derive(state, content)
    assert snapshot.click_event_mult == 777.0
    assert snapshot.cps == pytest.approx(100.0)
    assert snapshot.click_value == pytest.approx(777.0 + 1.0)


def test_golden_interval_multiplier_is_the_product_of_the_lures(
    state: GameState, content: ContentIndex
) -> None:
    state.upgrades_owned = {"up_golden_lure", "up_golden_beacon"}
    state.revision += 1
    assert derive(state, content).golden_interval_mult == pytest.approx(0.68)


def test_unknown_ids_in_state_are_ignored_rather_than_fatal(
    state: GameState, content: ContentIndex
) -> None:
    """A save from a version that had more content must still load and still compute."""
    state.owned = {"grandma": 1, "obsolete_building": 99}
    state.upgrades_owned = {"up_from_the_future"}
    state.achievements_unlocked = {"ach_from_the_future"}
    state.revision += 1
    snapshot = derive(state, content)
    assert snapshot.cps == pytest.approx(1.0)
    assert snapshot.achievement_mult == 1.0


def test_the_snapshot_is_cached_until_the_revision_changes(
    state: GameState, content: ContentIndex
) -> None:
    first = derive(state, content)
    assert derive(state, content) is first
    state.revision += 1
    assert derive(state, content) is not first


def test_baking_cookies_does_not_invalidate_the_snapshot(
    state: GameState, content: ContentIndex
) -> None:
    """Only things that change a term bump the revision; income does not."""
    state.owned = {"grandma": 1}
    state.revision += 1
    first = derive(state, content)
    state.cookies += 1_000.0
    state.all_time_cookies += 1_000.0
    assert derive(state, content) is first


def test_a_second_state_does_not_read_the_first_states_snapshot(
    state: GameState, content: ContentIndex
) -> None:
    state.owned = {"grandma": 10}
    state.revision += 1
    assert derive(state, content).cps == pytest.approx(10.0)

    other = dataclasses.replace(state, owned={"cursor": 1})
    assert derive(other, content).cps == pytest.approx(0.1)


def test_cache_can_be_dropped(state: GameState, content: ContentIndex) -> None:
    first = derive(state, content)
    derive_module.invalidate_cache()
    assert derive(state, content) is not first
