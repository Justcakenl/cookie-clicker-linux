"""Unlock evaluation: every condition fires once, and achievements are permanent."""

from __future__ import annotations

from cookie.engine.content import ContentIndex
from cookie.engine.specs import UnlockMetric
from cookie.engine.state import GameState
from cookie.engine.unlocks import REVEAL_FRACTION, evaluate_unlocks, is_available


def _satisfy(
    state: GameState,
    content: ContentIndex,
    metric: UnlockMetric,
    threshold: float,
    building: str | None,
) -> None:
    """Push one metric just past a threshold, touching nothing else."""
    match metric:
        case UnlockMetric.BUILDING_OWNED:
            assert building is not None
            state.owned[building] = int(threshold)
        case UnlockMetric.TOTAL_BUILDINGS:
            state.owned["cursor"] = int(threshold)
        case UnlockMetric.DISTINCT_BUILDINGS:
            for spec in content.buildings[: int(threshold)]:
                state.owned[spec.id] = 1
        case UnlockMetric.ALL_TIME_COOKIES:
            state.all_time_cookies = threshold
        case UnlockMetric.RUN_COOKIES:
            state.run_cookies = threshold
        case UnlockMetric.TOTAL_CLICKS:
            state.total_clicks = int(threshold)
        case UnlockMetric.CPS:
            state.owned["time_machine"] = max(1, int(threshold / 65_000_000.0) + 1)
        case UnlockMetric.GOLDEN_CAUGHT:
            state.golden_cookies_caught = int(threshold)
        case UnlockMetric.PRESTIGE_COUNT:
            state.prestige_count = int(threshold)
        case UnlockMetric.TIME_PLAYED:
            state.time_played = threshold
        case UnlockMetric.UPGRADES_OWNED:
            state.upgrades_owned = {f"filler_{index}" for index in range(int(threshold))}
        case UnlockMetric.OFFLINE_COOKIES:
            state.cookies_from_offline = threshold
    state.revision += 1


def test_a_fresh_game_has_earned_nothing(state: GameState, content: ContentIndex) -> None:
    delta = evaluate_unlocks(state, content)
    assert delta.new_achievements == ()
    assert delta.available_upgrades == ()
    assert delta.newly_revealed_buildings == ()
    assert state.revealed_buildings == {"cursor"}


def test_every_achievement_can_be_earned(state: GameState, content: ContentIndex) -> None:
    for achievement in content.achievements:
        fresh_state = state
        condition = achievement.unlock
        _satisfy(fresh_state, content, condition.metric, condition.threshold, condition.building)
        evaluate_unlocks(fresh_state, content)
        assert achievement.id in fresh_state.achievements_unlocked, achievement.id
    assert len(state.achievements_unlocked) == len(content.achievements)


def test_an_achievement_fires_exactly_once(state: GameState, content: ContentIndex) -> None:
    state.total_clicks = 10
    state.revision += 1
    first = evaluate_unlocks(state, content)
    assert "ach_clicks_10" in first.new_achievements

    second = evaluate_unlocks(state, content)
    assert "ach_clicks_10" not in second.new_achievements
    assert "ach_clicks_10" in state.achievements_unlocked


def test_an_achievement_survives_the_metric_collapsing(
    state: GameState, content: ContentIndex
) -> None:
    """A CPS milestone must survive the reset that a prestige performs."""
    state.owned = {"time_machine": 1}
    state.revision += 1
    evaluate_unlocks(state, content)
    assert "ach_cps_1m" in state.achievements_unlocked

    state.owned = {}
    state.revision += 1
    evaluate_unlocks(state, content)
    assert "ach_cps_1m" in state.achievements_unlocked


def test_every_upgrade_can_become_available(state: GameState, content: ContentIndex) -> None:
    seen: set[str] = set()
    for upgrade in content.upgrades:
        condition = upgrade.unlock
        _satisfy(state, content, condition.metric, condition.threshold, condition.building)
        # UPGRADES_OWNED conditions are satisfied with filler ids, which would otherwise mark real
        # upgrades as owned and hide them.
        state.upgrades_owned = {name for name in state.upgrades_owned if name.startswith("filler_")}
        state.revision += 1
        available = evaluate_unlocks(state, content).available_upgrades
        assert upgrade.id in available, upgrade.id
        seen.add(upgrade.id)
    assert len(seen) == len(content.upgrades)


def test_an_owned_upgrade_stops_being_available(state: GameState, content: ContentIndex) -> None:
    state.total_clicks = 10
    state.revision += 1
    assert "up_click_thimble" in evaluate_unlocks(state, content).available_upgrades

    state.upgrades_owned.add("up_click_thimble")
    state.revision += 1
    assert "up_click_thimble" not in evaluate_unlocks(state, content).available_upgrades
    assert not is_available("up_click_thimble", state, content)


def test_is_available_agrees_with_the_scan(state: GameState, content: ContentIndex) -> None:
    state.total_clicks = 300
    state.revision += 1
    available = set(evaluate_unlocks(state, content).available_upgrades)
    for upgrade in content.upgrades:
        assert is_available(upgrade.id, state, content) == (upgrade.id in available), upgrade.id


def test_is_available_rejects_unknown_ids(state: GameState, content: ContentIndex) -> None:
    assert not is_available("up_does_not_exist", state, content)


def test_buildings_reveal_at_half_their_sticker_price(
    state: GameState, content: ContentIndex
) -> None:
    grandma = content.building_by_id["grandma"]
    state.all_time_cookies = REVEAL_FRACTION * grandma.base_cost - 1.0
    state.revision += 1
    assert evaluate_unlocks(state, content).newly_revealed_buildings == ()

    state.all_time_cookies = REVEAL_FRACTION * grandma.base_cost
    state.revision += 1
    assert evaluate_unlocks(state, content).newly_revealed_buildings == ("grandma",)
    assert "grandma" in state.revealed_buildings


def test_reveals_are_monotone(state: GameState, content: ContentIndex) -> None:
    state.all_time_cookies = 1e13
    state.revision += 1
    evaluate_unlocks(state, content)
    revealed = set(state.revealed_buildings)
    assert len(revealed) >= 8

    state.all_time_cookies = 0.0
    state.revision += 1
    evaluate_unlocks(state, content)
    assert state.revealed_buildings == revealed


def test_reveals_are_reported_once(state: GameState, content: ContentIndex) -> None:
    state.all_time_cookies = 1e6
    state.revision += 1
    first = set(evaluate_unlocks(state, content).newly_revealed_buildings)
    assert first
    assert evaluate_unlocks(state, content).newly_revealed_buildings == ()


def test_a_scan_that_changes_nothing_does_not_bump_the_revision(
    state: GameState, content: ContentIndex
) -> None:
    """The revision is the derive cache key, so a quiet scan must not invalidate it."""
    before = state.revision
    evaluate_unlocks(state, content)
    assert state.revision == before


def test_achievement_order_follows_the_content_table(
    state: GameState, content: ContentIndex
) -> None:
    """Crossing several thresholds at once must produce a stable toast order."""
    state.total_clicks = 10_000
    state.revision += 1
    earned = evaluate_unlocks(state, content).new_achievements
    order = [spec.id for spec in content.achievements]
    assert list(earned) == [spec_id for spec_id in order if spec_id in set(earned)]
