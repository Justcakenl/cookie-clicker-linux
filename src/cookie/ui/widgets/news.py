"""A one-line ticker that reacts to how the run is going.

It exists because this game spends most of its life in a window nobody is looking at directly. A
line that changes on its own, and that comments on what you actually own, is what makes a glance
worth taking.
"""

from __future__ import annotations

import dataclasses
from typing import Final

from textual.widgets import Static

from cookie.engine import rng
from cookie.engine.content import ContentIndex
from cookie.engine.state import GameState

ROTATE_AFTER: Final[float] = 12.0
STREAM: Final[str] = "news"


@dataclasses.dataclass(frozen=True, slots=True)
class Headline:
    """A line, and what has to be true for it to be worth printing."""

    text: str
    building: str | None = None
    min_owned: int = 0
    min_all_time: float = 0.0
    min_prestige: int = 0


# Ordered loosely by when they become eligible. Anything gated on a building only appears once that
# building is owned, so the ticker never mentions a Portal to someone with three Cursors.
HEADLINES: Final[tuple[Headline, ...]] = (
    Headline("The oven is warm. Nothing else has happened yet."),
    Headline("Local baker denies everything, continues baking."),
    Headline("Study finds cookies improve mood; funding withdrawn."),
    Headline("Neighbours describe the smell as 'constant'."),
    Headline("Cursor union files first grievance.", building="cursor", min_owned=25),
    Headline("Cursors reportedly clicking in their sleep.", building="cursor", min_owned=100),
    Headline("Grandmas seen exchanging glances.", building="grandma", min_owned=15),
    Headline(
        "Grandmas have formed a committee. Minutes unavailable.", building="grandma", min_owned=50
    ),
    Headline("Grandmas ask whether you have eaten today.", building="grandma", min_owned=100),
    Headline(
        "Cookie farm accused of monoculture; farm unrepentant.", building="farm", min_owned=10
    ),
    Headline("Mine reaches a layer that tastes faintly of vanilla.", building="mine", min_owned=10),
    Headline("Factory posts record output and a safety notice.", building="factory", min_owned=10),
    Headline("Bank offers cookies as collateral against cookies.", building="bank", min_owned=5),
    Headline("Temple declares a surplus and a festival.", building="temple", min_owned=5),
    Headline(
        "Wizard tower insists the smoke is intentional.", building="wizard_tower", min_owned=5
    ),
    Headline("Shipment arrives early. Nobody ordered it.", building="shipment", min_owned=5),
    Headline("Alchemy lab converts gold at a loss, proudly.", building="alchemy_lab", min_owned=5),
    Headline("Portal humming in a key nobody recognises.", building="portal", min_owned=3),
    Headline(
        "Time machine delivers tomorrow's batch. It is fine.", building="time_machine", min_owned=3
    ),
    Headline(
        "Antimatter condenser asks for a wider berth.", building="antimatter_condenser", min_owned=3
    ),
    Headline("Prism accused of making cookies out of daylight.", building="prism", min_owned=3),
    Headline("Chancemaker wins a raffle it also organised.", building="chancemaker", min_owned=3),
    Headline(
        "Fractal engine reports infinite progress, so far.", building="fractal_engine", min_owned=3
    ),
    Headline("Server farm now warmer than the actual ovens.", building="server_farm", min_owned=3),
    Headline(
        "Idleverse continues to do nothing, extremely well.", building="idleverse", min_owned=3
    ),
    Headline(
        "Cortex baker has started finishing your sentences.", building="cortex_baker", min_owned=3
    ),
    Headline(
        "Dyson oven blamed for unseasonably warm evening.", building="dyson_oven", min_owned=3
    ),
    Headline(
        "Ouroboros mill audited; auditors found themselves.", building="ouroboros_mill", min_owned=3
    ),
    Headline(
        "Quantum bakery both open and closed for business.", building="quantum_bakery", min_owned=3
    ),
    Headline("Hive mind reaches unanimous verdict on biscuits.", building="hive_mind", min_owned=3),
    Headline("Chronofurnace running late and also early.", building="chronofurnace", min_owned=3),
    Headline(
        "Singularity press denies pulling in the neighbours.",
        building="singularity_press",
        min_owned=3,
    ),
    Headline(
        "Dream kitchen produced something nobody can describe.",
        building="dream_kitchen",
        min_owned=3,
    ),
    Headline("The Last Oven remains lit. No further comment.", building="last_oven", min_owned=1),
    Headline("Void bakery reports nothing, at scale.", building="void_bakery", min_owned=1),
    Headline(
        "Eschaton mill asks you not to worry about it.", building="eschaton_mill", min_owned=1
    ),
    Headline(
        "Godshard furnace described as 'regrettably efficient'.",
        building="godshard_furnace",
        min_owned=1,
    ),
    Headline(
        "First Cause files for retroactive planning permission.",
        building="first_cause",
        min_owned=1,
    ),
    Headline(
        "The Recipe has been followed. Nothing has ended.", building="the_recipe", min_owned=1
    ),
    Headline("Economists puzzled by cookie-denominated economy.", min_all_time=1e9),
    Headline("Cookie output now visible from orbit.", min_all_time=1e15),
    Headline("Historians divide time into before and after you.", min_all_time=1e21),
    Headline("Reality asks politely whether you are finished.", min_all_time=1e30),
    Headline("You remember a previous life. It baked less.", min_prestige=1),
    Headline("Veterans of earlier bakeries speak of you warmly.", min_prestige=5),
)


def eligible(state: GameState, content: ContentIndex) -> tuple[Headline, ...]:
    """The headlines that make sense for this save right now."""
    return tuple(
        headline
        for headline in HEADLINES
        if state.all_time_cookies >= headline.min_all_time
        and state.prestige_count >= headline.min_prestige
        and (
            headline.building is None
            or (
                headline.building in content.building_by_id
                and state.owned.get(headline.building, 0) >= headline.min_owned
            )
        )
    )


def pick(state: GameState, content: ContentIndex, slot: int) -> str:
    """The headline for a given slot, drawn from the save's own seed.

    Slots come from `time_played`, so two runs with the same seed read the same news, and the ticker
    cannot become a source of nondeterminism in a game that is otherwise reproducible.
    """
    candidates = eligible(state, content)
    if not candidates:
        return HEADLINES[0].text
    draw = rng.unit(state.rng_seed, STREAM, slot)
    return candidates[min(int(draw * len(candidates)), len(candidates) - 1)].text


class NewsTicker(Static):
    """One line, replaced every ROTATE_AFTER seconds of play."""

    def __init__(self) -> None:
        super().__init__(id="news-line")
        self._slot = -1

    def update_for(self, state: GameState, content: ContentIndex) -> None:
        slot = int(state.time_played // ROTATE_AFTER)
        if slot == self._slot:
            return
        self._slot = slot
        self.update(pick(state, content, slot))
