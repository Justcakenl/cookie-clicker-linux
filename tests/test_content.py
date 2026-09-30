"""Content table integrity, per docs/ARCHITECTURE.md §12 and the counts in docs/BALANCE.md."""

from __future__ import annotations

import itertools

from cookie.engine.content import (
    ACHIEVEMENT_CPS_BONUS,
    ACHIEVEMENTS,
    BUILDINGS,
    CONTENT,
    GOLDEN_EFFECTS,
    MILESTONE_COST_FACTOR,
    UPGRADES,
)
from cookie.engine.numbers import format_short
from cookie.engine.specs import AchievementSpec, EffectSlot, UnlockMetric, UpgradeKind, UpgradeSpec

EXPECTED_BUILDING_IDS = (
    "cursor",
    "grandma",
    "farm",
    "mine",
    "factory",
    "bank",
    "temple",
    "wizard_tower",
    "shipment",
    "alchemy_lab",
    "portal",
    "time_machine",
    "antimatter_condenser",
    "prism",
    "chancemaker",
    "fractal_engine",
    "server_farm",
    "idleverse",
    "cortex_baker",
    "dyson_oven",
    "ouroboros_mill",
    "quantum_bakery",
    "hive_mind",
    "chronofurnace",
    "singularity_press",
    "dream_kitchen",
    "last_oven",
    "void_bakery",
    "eschaton_mill",
    "godshard_furnace",
    "first_cause",
    "the_recipe",
)


def test_documented_table_sizes() -> None:
    assert len(BUILDINGS) == 32
    assert len(UPGRADES) == 184
    assert len(ACHIEVEMENTS) == 91
    assert len(GOLDEN_EFFECTS) == 5


def test_ids_are_unique_across_every_table() -> None:
    ids = [spec.id for spec in BUILDINGS]
    ids += [spec.id for spec in UPGRADES]
    ids += [spec.id for spec in ACHIEVEMENTS]
    ids += [spec.id for spec in GOLDEN_EFFECTS]
    duplicates = {value for value in ids if ids.count(value) > 1}
    assert not duplicates, f"duplicate ids: {sorted(duplicates)}"


def test_buildings_are_in_tier_order_with_rising_cost() -> None:
    assert tuple(spec.id for spec in BUILDINGS) == EXPECTED_BUILDING_IDS
    for index, spec in enumerate(BUILDINGS, start=1):
        assert spec.tier == index
        assert spec.base_cps > 0.0
        assert spec.base_cost > 0.0
        assert spec.name
        assert spec.flavor
    for earlier, later in itertools.pairwise(BUILDINGS):
        assert later.base_cost > earlier.base_cost
        assert later.base_cps > earlier.base_cps


def test_cost_per_cps_rises_from_the_second_tier_onward() -> None:
    """Grandma is deliberately a better deal than Cursor; after that each tier is a longer bet."""
    ratios = [spec.base_cost / spec.base_cps for spec in BUILDINGS]
    assert ratios[1] < ratios[0]
    for earlier, later in itertools.pairwise(ratios[1:]):
        assert later > earlier


def test_upgrade_targets_and_kinds_agree() -> None:
    building_ids = {spec.id for spec in BUILDINGS}
    for upgrade in UPGRADES:
        assert upgrade.name
        assert upgrade.flavor
        assert upgrade.cost > 0.0
        if upgrade.kind is UpgradeKind.BUILDING_MULT:
            assert upgrade.target_building in building_ids
        else:
            assert upgrade.target_building is None


def test_building_multiplier_group_is_complete_and_priced_by_the_formula() -> None:
    per_building: dict[str, list[UpgradeSpec]] = {spec.id: [] for spec in BUILDINGS}
    base_cost = {spec.id: spec.base_cost for spec in BUILDINGS}
    for upgrade in UPGRADES:
        if upgrade.kind is not UpgradeKind.BUILDING_MULT:
            continue
        assert upgrade.target_building is not None
        per_building[upgrade.target_building].append(upgrade)

    for building_id, upgrades in per_building.items():
        milestones = sorted(int(upgrade.unlock.threshold) for upgrade in upgrades)
        assert milestones == [1, 5, 25, 50, 100], building_id
        for upgrade in upgrades:
            milestone = int(upgrade.unlock.threshold)
            assert upgrade.magnitude == 2.0
            assert upgrade.unlock.metric is UnlockMetric.BUILDING_OWNED
            assert upgrade.unlock.building == building_id
            assert upgrade.cost == base_cost[building_id] * MILESTONE_COST_FACTOR[milestone]
            assert upgrade.id == f"up_{building_id}_{milestone}"


def test_upgrade_group_counts_sum_to_the_documented_total() -> None:
    counts = dict.fromkeys(UpgradeKind, 0)
    for upgrade in UPGRADES:
        counts[upgrade.kind] += 1
    click_kinds = (UpgradeKind.CLICK_FLAT, UpgradeKind.CLICK_MULT, UpgradeKind.CLICK_CPS_SHARE)
    assert counts[UpgradeKind.BUILDING_MULT] == 5 * len(BUILDINGS) == 160
    assert sum(counts[kind] for kind in click_kinds) == 10
    assert counts[UpgradeKind.GLOBAL_MULT] == 12
    assert counts[UpgradeKind.GOLDEN_INTERVAL] == 2
    assert sum(counts.values()) == 184


def test_click_cps_share_total_matches_the_documented_end_game_share() -> None:
    share = sum(u.magnitude for u in UPGRADES if u.kind is UpgradeKind.CLICK_CPS_SHARE)
    assert share == 0.15


def test_golden_interval_upgrades_shorten_the_wait() -> None:
    lures = [u for u in UPGRADES if u.kind is UpgradeKind.GOLDEN_INTERVAL]
    assert len(lures) == 2
    for lure in lures:
        assert 0.0 < lure.magnitude < 1.0


def test_every_unlock_condition_is_well_formed() -> None:
    building_ids = {spec.id for spec in BUILDINGS}
    specs: tuple[UpgradeSpec | AchievementSpec, ...] = (*UPGRADES, *ACHIEVEMENTS)
    for spec in specs:
        condition = spec.unlock
        assert condition.threshold > 0.0
        if condition.metric is UnlockMetric.BUILDING_OWNED:
            assert condition.building in building_ids
        else:
            assert condition.building is None


def test_achievements_cover_every_metric_and_share_one_bonus() -> None:
    used = {spec.unlock.metric for spec in ACHIEVEMENTS}
    assert used == set(UnlockMetric), f"unused metrics: {sorted(set(UnlockMetric) - used)}"
    for spec in ACHIEVEMENTS:
        assert spec.cps_bonus == ACHIEVEMENT_CPS_BONUS
        assert spec.name
        assert spec.description.endswith(".")
    total = sum(spec.cps_bonus for spec in ACHIEVEMENTS)
    assert round(total, 10) == 0.91


def test_golden_weights_sum_to_one_hundred_and_slots_are_consistent() -> None:
    assert sum(spec.weight for spec in GOLDEN_EFFECTS) == 100
    assert CONTENT.golden_weight_total == 100
    for spec in GOLDEN_EFFECTS:
        assert spec.weight > 0
        assert spec.message
        if spec.slot is EffectSlot.INSTANT:
            assert spec.duration == 0.0
            assert spec.lump_fraction > 0.0 or spec.lump_flat > 0.0
        else:
            assert spec.duration > 0.0
            assert spec.magnitude > 1.0
            assert spec.lump_fraction == 0.0
            assert spec.lump_cps_seconds == 0.0
            assert spec.lump_flat == 0.0


def test_index_lookups_agree_with_the_tables() -> None:
    assert set(CONTENT.building_by_id) == {spec.id for spec in BUILDINGS}
    assert set(CONTENT.upgrade_by_id) == {spec.id for spec in UPGRADES}
    assert set(CONTENT.achievement_by_id) == {spec.id for spec in ACHIEVEMENTS}
    for building in BUILDINGS:
        targeted = CONTENT.upgrades_for_building[building.id]
        assert len(targeted) == 5
        assert all(upgrade.target_building == building.id for upgrade in targeted)


def test_content_tables_are_immutable() -> None:
    assert isinstance(BUILDINGS, tuple)
    assert isinstance(UPGRADES, tuple)
    assert isinstance(ACHIEVEMENTS, tuple)
    assert isinstance(GOLDEN_EFFECTS, tuple)


def test_the_completion_achievements_track_the_real_totals() -> None:
    """These two are the ones that silently become unreachable when content grows."""
    by_id = {spec.id: spec for spec in ACHIEVEMENTS}
    assert by_id["ach_upgrades_all"].unlock.threshold == len(UPGRADES)
    assert by_id["ach_distinct_32"].unlock.threshold == len(BUILDINGS)


def test_the_last_five_tiers_are_deliberately_steeper() -> None:
    """docs/BALANCE.md §1 promises the endgame leaves the curve. Hold it to that."""
    ratios = [
        BUILDINGS[index + 1].base_cost / BUILDINGS[index].base_cost
        for index in range(len(BUILDINGS) - 1)
    ]
    middle = ratios[1:26]
    endgame = ratios[26:]
    assert max(middle) < 17.0
    assert min(endgame) > 50.0


def test_no_building_cost_reaches_the_formatter_ceiling() -> None:
    """The most expensive upgrade must still render, not fall off the end of the scale table."""
    dearest = max(spec.cost for spec in UPGRADES)
    rendered = format_short(dearest)
    assert rendered
    assert len(rendered) <= 17
