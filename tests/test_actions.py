"""Player actions: conservation of cookies, validation, and prestige scope."""

from __future__ import annotations

import pytest

from cookie.engine import costs
from cookie.engine.actions import (
    buy_building,
    buy_upgrade,
    click,
    do_prestige,
    hard_reset,
    prestige_preview,
    resolve_buy_count,
)
from cookie.engine.content import ContentIndex
from cookie.engine.derive import derive
from cookie.engine.errors import InsufficientCookiesError, InvalidStateError, UnknownIdError
from cookie.engine.state import GameState, new_game
from cookie.engine.unlocks import evaluate_unlocks
from tests.conftest import SEED

PRESERVED_BY_PRESTIGE = (
    "all_time_cookies",
    "total_clicks",
    "time_played",
    "cookies_from_clicks",
    "cookies_from_offline",
    "cookies_from_golden",
    "max_cps_seen",
    "buildings_bought_total",
    "rng_seed",
    "started_at",
)


def test_a_click_bakes_exactly_the_click_value(state: GameState, content: ContentIndex) -> None:
    expected = derive(state, content).click_value
    result = click(state, content)
    assert result.cookies_gained == pytest.approx(expected)
    assert state.cookies == pytest.approx(expected)
    assert state.cookies_from_clicks == pytest.approx(expected)
    assert state.all_time_cookies == pytest.approx(expected)
    assert state.total_clicks == 1


def test_clicks_accumulate_and_earn_their_achievement(
    state: GameState, content: ContentIndex
) -> None:
    for _ in range(9):
        click(state, content)
    assert "ach_clicks_10" not in state.achievements_unlocked
    result = click(state, content)
    assert "ach_clicks_10" in result.delta.new_achievements
    assert state.total_clicks == 10


def test_buying_charges_the_bulk_price_and_grants_the_count(
    state: GameState, content: ContentIndex
) -> None:
    state.cookies = 10_000.0
    expected = costs.bulk_cost(15.0, 0, 10)
    result = buy_building(state, content, "cursor", 10)
    assert result.cost == expected
    assert result.count == 10
    assert state.cookies == pytest.approx(10_000.0 - expected)
    assert state.owned["cursor"] == 10
    assert state.buildings_bought_total == 10


def test_buying_in_bulk_is_never_dearer_than_buying_singly(
    state: GameState, content: ContentIndex
) -> None:
    """Rounding once instead of ten times makes "buy 10" cheaper by at most ten cookies.

    docs/BALANCE.md §2.2 chooses that on purpose: the alternative is a per-unit ceiling that breaks
    the identity max_affordable is solved against. The gap is bounded by the count.
    """
    singly = state
    singly.cookies = 10_000.0
    for _ in range(10):
        buy_building(singly, content, "cursor", 1)
    spent_singly = 10_000.0 - singly.cookies

    bulk = new_game(seed=SEED, now=0.0)
    bulk.cookies = 10_000.0
    spent_bulk = buy_building(bulk, content, "cursor", 10).cost

    assert spent_bulk <= spent_singly <= spent_bulk + 10
    assert singly.owned["cursor"] == bulk.owned["cursor"] == 10


def test_a_failed_purchase_changes_nothing(state: GameState, content: ContentIndex) -> None:
    state.cookies = 14.0
    with pytest.raises(InsufficientCookiesError):
        buy_building(state, content, "cursor", 1)
    assert state.cookies == 14.0
    assert state.owned == {}
    assert state.buildings_bought_total == 0


def test_buy_validation(state: GameState, content: ContentIndex) -> None:
    state.cookies = 1e30
    with pytest.raises(UnknownIdError):
        buy_building(state, content, "not_a_building", 1)
    with pytest.raises(InvalidStateError):
        buy_building(state, content, "cursor", 0)
    with pytest.raises(InvalidStateError):
        buy_building(state, content, "cursor", -5)
    with pytest.raises(InvalidStateError):
        buy_building(state, content, "cursor", costs.MAX_BULK + 1)


def test_resolve_buy_count_matches_max_affordable(state: GameState, content: ContentIndex) -> None:
    state.cookies = 1_000.0
    assert resolve_buy_count(state, content, "cursor", 1) == 1
    assert resolve_buy_count(state, content, "cursor", 100) == 100
    assert resolve_buy_count(state, content, "cursor", "max") == costs.max_affordable(
        15.0, 0, 1_000.0
    )
    assert resolve_buy_count(state, content, "grandma", "max") == costs.max_affordable(
        100.0, 0, 1_000.0
    )


def test_buying_max_with_nothing_resolves_to_zero_and_is_refused(
    state: GameState, content: ContentIndex
) -> None:
    count = resolve_buy_count(state, content, "cursor", "max")
    assert count == 0
    with pytest.raises(InvalidStateError):
        buy_building(state, content, "cursor", count)


def test_an_upgrade_must_be_unlocked_owned_once_and_paid_for(
    state: GameState, content: ContentIndex
) -> None:
    state.cookies = 1e6
    with pytest.raises(InvalidStateError):
        buy_upgrade(state, content, "up_click_thimble")

    state.total_clicks = 10
    state.revision += 1
    result = buy_upgrade(state, content, "up_click_thimble")
    assert result.cost == 100.0
    assert "up_click_thimble" in state.upgrades_owned
    assert state.cookies == pytest.approx(1e6 - 100.0)

    with pytest.raises(InvalidStateError):
        buy_upgrade(state, content, "up_click_thimble")
    with pytest.raises(UnknownIdError):
        buy_upgrade(state, content, "up_nonexistent")


def test_an_unaffordable_upgrade_is_refused_without_side_effects(
    state: GameState, content: ContentIndex
) -> None:
    state.total_clicks = 10
    state.cookies = 99.0
    state.revision += 1
    with pytest.raises(InsufficientCookiesError):
        buy_upgrade(state, content, "up_click_thimble")
    assert state.upgrades_owned == set()
    assert state.cookies == 99.0


def test_validating_an_upgrade_does_not_award_achievements(
    state: GameState, content: ContentIndex
) -> None:
    """The availability check must be read-only, or a refused purchase would still pay out."""
    state.total_clicks = 10
    state.cookies = 0.0
    state.revision += 1
    with pytest.raises(InsufficientCookiesError):
        buy_upgrade(state, content, "up_click_thimble")
    assert state.achievements_unlocked == set()


def test_buying_an_upgrade_raises_cps(state: GameState, content: ContentIndex) -> None:
    state.owned = {"cursor": 1}
    state.cookies = 1_000.0
    state.revision += 1
    before = derive(state, content).base_cps
    buy_upgrade(state, content, "up_cursor_1")
    assert derive(state, content).base_cps == pytest.approx(before * 2.0)


def test_prestige_preview_reports_the_trade_without_changing_anything(
    state: GameState, content: ContentIndex
) -> None:
    state.all_time_cookies = 8e9
    state.cookies = 1_234.0
    state.owned = {"cursor": 5}
    state.upgrades_owned = {"up_cursor_1"}
    state.revision += 1
    snapshot = vars_snapshot(state)

    preview = prestige_preview(state, content)
    assert preview.chips_available == 2
    assert preview.chips_held == 0
    assert preview.chips_gained == 2
    assert preview.multiplier_after == pytest.approx(1.10)
    assert preview.cookies_lost == 1_234.0
    assert preview.buildings_lost == {"cursor": 5}
    assert preview.upgrades_lost == 1
    assert preview.is_worthwhile
    assert vars_snapshot(state) == snapshot


def test_prestige_preview_says_how_far_the_next_chip_is(
    state: GameState, content: ContentIndex
) -> None:
    state.all_time_cookies = 5e8
    state.revision += 1
    preview = prestige_preview(state, content)
    assert preview.chips_available == 0
    assert not preview.is_worthwhile
    assert preview.cookies_until_next_chip == pytest.approx(1e9 - 5e8)


def test_prestige_resets_the_run_and_keeps_the_record(
    state: GameState, content: ContentIndex
) -> None:
    state.all_time_cookies = 1e12
    state.run_cookies = 1e12
    state.cookies = 5e11
    state.owned = {"cursor": 100, "grandma": 40}
    state.upgrades_owned = {"up_cursor_1", "up_grandma_1"}
    state.achievements_unlocked = {"ach_clicks_10"}
    state.total_clicks = 321
    state.time_played = 9_000.0
    state.buildings_bought_total = 140
    state.revision += 1
    preserved = {field: getattr(state, field) for field in PRESERVED_BY_PRESTIGE}

    do_prestige(state, content)

    assert state.heavenly_chips == 10
    assert state.prestige_count == 1
    assert state.cookies == 0.0
    assert state.run_cookies == 0.0
    assert state.owned == {}
    assert state.upgrades_owned == set()
    assert state.active_effects == []
    assert "ach_clicks_10" in state.achievements_unlocked
    assert "ach_prestige_1" in state.achievements_unlocked
    for field, value in preserved.items():
        assert getattr(state, field) == value, field


def test_prestige_keeps_revealed_buildings(state: GameState, content: ContentIndex) -> None:
    """The gate reads all-time cookies, which survive, so re-hiding would last one tick."""
    state.all_time_cookies = 1e12
    state.revision += 1
    evaluate_unlocks(state, content)
    revealed = set(state.revealed_buildings)
    assert len(revealed) > 1

    do_prestige(state, content)
    assert state.revealed_buildings == revealed


def test_prestige_multiplier_applies_to_the_rebuilt_run(
    state: GameState, content: ContentIndex
) -> None:
    state.all_time_cookies = 1e12
    state.revision += 1
    do_prestige(state, content)
    state.owned = {"grandma": 10}
    state.revision += 1
    snapshot = derive(state, content)
    assert snapshot.prestige_mult == pytest.approx(1.50)
    assert snapshot.cps == pytest.approx(10.0 * 1.50 * snapshot.achievement_mult)


def test_prestige_is_refused_when_it_would_gain_nothing(
    state: GameState, content: ContentIndex
) -> None:
    with pytest.raises(InvalidStateError):
        do_prestige(state, content)

    state.all_time_cookies = 1e12
    state.heavenly_chips = 10
    state.revision += 1
    with pytest.raises(InvalidStateError):
        do_prestige(state, content)


def test_hard_reset_clears_progress_but_keeps_settings(state: GameState) -> None:
    state.all_time_cookies = 1e12
    state.heavenly_chips = 10
    state.prestige_count = 3
    state.achievements_unlocked = {"ach_clicks_10"}
    state.settings.number_format = "scientific"
    state.settings.animations = False

    fresh = hard_reset(state, now=123.0)
    assert fresh.all_time_cookies == 0.0
    assert fresh.heavenly_chips == 0
    assert fresh.prestige_count == 0
    assert fresh.achievements_unlocked == set()
    assert fresh.started_at == 123.0
    assert fresh.settings.number_format == "scientific"
    assert fresh.settings.animations is False


def vars_snapshot(state: GameState) -> dict[str, object]:
    return {
        field: repr(getattr(state, field)) for field in GameState.__slots__ if field != "settings"
    }
