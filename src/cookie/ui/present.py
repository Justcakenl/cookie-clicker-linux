"""State to view data. Pure functions, so what the screen shows can be tested without a screen."""

from __future__ import annotations

from cookie.engine import costs
from cookie.engine.actions import BuyAmount, resolve_buy_count
from cookie.engine.content import ContentIndex
from cookie.engine.derive import derive
from cookie.engine.specs import EffectSlot
from cookie.engine.state import GameState
from cookie.ui.widgets.shop import BuildingRowData


def building_rows(
    state: GameState, content: ContentIndex, amount: BuyAmount
) -> list[BuildingRowData]:
    """One row per building, in tier order, always all of them."""
    snapshot = derive(state, content)
    total = snapshot.base_cps
    rows: list[BuildingRowData] = []
    for spec in content.buildings:
        owned = state.owned.get(spec.id, 0)
        # Owning one is proof enough: a row must never show ??? for something already bought.
        revealed = spec.id in state.revealed_buildings or owned > 0
        count = resolve_buy_count(state, content, spec.id, amount)
        cost = costs.bulk_cost(spec.base_cost, owned, max(count, 1))
        contribution = snapshot.building_cps[spec.id] * snapshot.global_upgrade_mult
        contribution *= snapshot.achievement_mult * snapshot.prestige_mult
        rows.append(
            BuildingRowData(
                building_id=spec.id,
                name=spec.name,
                owned=owned,
                cost=cost,
                contribution=contribution,
                share=snapshot.building_cps[spec.id] / total if total > 0.0 else 0.0,
                affordable=count > 0 and cost <= state.cookies,
                revealed=revealed,
                flavor=spec.flavor,
            )
        )
    return rows


def upgrade_entries(
    content: ContentIndex, available: tuple[str, ...]
) -> list[tuple[str, str, float]]:
    """Available upgrades as (id, name, cost), cheapest first."""
    entries = [
        (upgrade_id, spec.name, spec.cost)
        for upgrade_id in available
        if (spec := content.upgrade_by_id.get(upgrade_id)) is not None
    ]
    entries.sort(key=lambda entry: entry[2])
    return entries


def best_affordable_building(state: GameState, content: ContentIndex) -> str | None:
    """The affordable building with the best price per cookie per second.

    This is the same rule the pacing simulation uses, so the "buy best" key and the reference policy
    cannot drift apart.
    """
    snapshot = derive(state, content)
    best: tuple[float, int, str] | None = None
    for spec in content.buildings:
        if spec.id not in state.revealed_buildings:
            continue
        owned = state.owned.get(spec.id, 0)
        price = costs.unit_cost(spec.base_cost, owned)
        if price > state.cookies:
            continue
        marginal = spec.base_cps * snapshot.building_mult[spec.id]
        if marginal <= 0.0:
            continue
        candidate = (price / marginal, spec.tier, spec.id)
        if best is None or candidate < best:
            best = candidate
    return None if best is None else best[2]


def active_event(state: GameState) -> tuple[str, float]:
    """The running timed effect as a label and its remaining seconds, or no label."""
    for effect in state.active_effects:
        if effect.slot is EffectSlot.CPS_MULT:
            return f"x{effect.magnitude:g} frenzy", effect.remaining
    for effect in state.active_effects:
        if effect.slot is EffectSlot.CLICK_MULT:
            return f"x{effect.magnitude:g} clicks", effect.remaining
    return "", 0.0
