"""The RP-1 reference policy of docs/BALANCE.md §8.1, as a driver the pacing test runs.

Not a test. It exists so the policy is written once and the assertions elsewhere are only bands.
"""

from __future__ import annotations

import dataclasses
from typing import Final

from cookie.engine import costs, prestige
from cookie.engine.actions import buy_building, buy_upgrade, catch_golden, click
from cookie.engine.content import CONTENT, ContentIndex
from cookie.engine.derive import derive
from cookie.engine.specs import UpgradeKind
from cookie.engine.state import GameState, GoldenPhase, new_game
from cookie.engine.tick import FIXED_DT, advance
from cookie.engine.unlocks import available_upgrades

SEED: Final[int] = 20260927
CLICKS_PER_SECOND: Final[int] = 5
CLICK_UNTIL: Final[float] = 120.0
DECISION_INTERVAL: Final[float] = 5.0
CATCH_DELAY: Final[float] = 1.0
DEFAULT_LIMIT: Final[float] = 6.0 * 3_600.0

# The order upgrades are considered in, cheapest first within each group.
_UPGRADE_GROUPS: Final[tuple[tuple[UpgradeKind, ...], ...]] = (
    (UpgradeKind.BUILDING_MULT,),
    (UpgradeKind.CLICK_FLAT, UpgradeKind.CLICK_MULT, UpgradeKind.CLICK_CPS_SHARE),
    (UpgradeKind.GLOBAL_MULT,),
    (UpgradeKind.GOLDEN_INTERVAL,),
)


@dataclasses.dataclass(frozen=True, slots=True)
class RunResult:
    state: GameState
    milestones: dict[str, float]

    def at(self, milestone: str) -> float | None:
        return self.milestones.get(milestone)


def _steps_per_click() -> int:
    """Two steps between clicks at 5 per second and a tenth-second step."""
    return round(1.0 / (CLICKS_PER_SECOND * FIXED_DT))


def _buy_upgrades(state: GameState, content: ContentIndex) -> None:
    """Every affordable available upgrade, group by group, cheapest first within a group."""
    for kinds in _UPGRADE_GROUPS:
        while True:
            candidates = [
                content.upgrade_by_id[upgrade_id]
                for upgrade_id in available_upgrades(state, content)
                if content.upgrade_by_id[upgrade_id].kind in kinds
                and content.upgrade_by_id[upgrade_id].cost <= state.cookies
            ]
            if not candidates:
                break
            cheapest = min(candidates, key=lambda spec: (spec.cost, spec.id))
            buy_upgrade(state, content, cheapest.id)


def _buy_buildings(state: GameState, content: ContentIndex) -> None:
    """One unit at a time, always the best price per marginal cookie per second."""
    while True:
        snapshot = derive(state, content)
        best: tuple[float, int, str] | None = None
        for spec in content.buildings:
            owned = state.owned.get(spec.id, 0)
            price = costs.unit_cost(spec.base_cost, owned)
            if price > state.cookies:
                continue
            marginal = spec.base_cps * snapshot.building_mult[spec.id]
            candidate = (price / marginal, spec.tier, spec.id)
            if best is None or candidate < best:
                best = candidate
        if best is None:
            return
        buy_building(state, content, best[2], 1)


def run(
    *,
    seed: int = SEED,
    limit: float = DEFAULT_LIMIT,
    content: ContentIndex = CONTENT,
) -> RunResult:
    """Play the reference policy and record when each milestone was first reached."""
    state = new_game(seed=seed, now=0.0)
    milestones: dict[str, float] = {}
    steps_per_click = _steps_per_click()
    decision_steps = round(DECISION_INTERVAL / FIXED_DT)
    catch_at: float | None = None
    step = 0

    def mark(name: str) -> None:
        milestones.setdefault(name, state.time_played)

    while state.time_played < limit:
        if state.time_played < CLICK_UNTIL and step % steps_per_click == 0:
            click(state, content)

        advance(state, FIXED_DT, content=content)
        step += 1

        if state.golden_phase is GoldenPhase.VISIBLE:
            if catch_at is None:
                catch_at = state.time_played + CATCH_DELAY
            elif state.time_played >= catch_at:
                catch_golden(state, content)
                catch_at = None
        else:
            catch_at = None

        if step % decision_steps == 0:
            _buy_upgrades(state, content)
            _buy_buildings(state, content)

        for spec in content.buildings:
            if state.owned.get(spec.id, 0) >= 1:
                mark(f"first_{spec.id}")
        if state.owned.get("cursor", 0) >= 10:
            mark("ten_cursors")
        for threshold, name in (
            (1e3, "baked_1e3"),
            (1e6, "baked_1e6"),
            (1e9, "baked_1e9"),
        ):
            if state.all_time_cookies >= threshold:
                mark(name)
        if prestige.chips_for(state.all_time_cookies) >= 1:
            mark("first_chip")

    return RunResult(state=state, milestones=milestones)
