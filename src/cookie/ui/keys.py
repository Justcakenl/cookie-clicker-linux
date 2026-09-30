"""The single keybinding table. The footer and the help screen both read it from here."""

from __future__ import annotations

import dataclasses
from typing import Final

from textual.binding import Binding


@dataclasses.dataclass(frozen=True, slots=True)
class KeyHelp:
    """One row of the help screen."""

    keys: str
    action: str
    group: str


# A binding declared on a node resolves its action against that same node, so the split below is
# not cosmetic: screen actions live on MainScreen and these live on CookieApp.
GAME_BINDINGS: Final[tuple[Binding, ...]] = (
    Binding("space", "bake", "Bake", priority=True),
    Binding("enter", "bake", "Bake", show=False),
    Binding("g", "catch_golden", "Catch", show=False),
    Binding("1", "buy_amount('1')", "Buy 1", show=False),
    Binding("2", "buy_amount('10')", "Buy 10", show=False),
    Binding("3", "buy_amount('100')", "Buy 100", show=False),
    Binding("4", "buy_amount('max')", "Buy max", show=False),
    Binding("x", "buy_selected", "Buy"),
    Binding("b", "buy_best", "Buy best", show=False),
    Binding("u", "buy_upgrade", "Upgrade", show=False),
)

APP_BINDINGS: Final[tuple[Binding, ...]] = (
    Binding("s", "stats", "Stats"),
    Binding("a", "achievements", "Awards"),
    Binding("p", "prestige", "Ascend"),
    Binding("comma", "settings", "Settings", key_display=","),
    Binding("question_mark", "help", "Help", key_display="?"),
    Binding("q", "quit", "Quit"),
    Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
)

MODAL_BINDINGS: Final[tuple[Binding, ...]] = (
    Binding("escape", "close", "Close"),
    Binding("q", "close", "Close", show=False),
)

HELP_ROWS: Final[tuple[KeyHelp, ...]] = (
    KeyHelp("space, enter", "Bake one cookie by hand", "Baking"),
    KeyHelp("click the cookie", "Bake one cookie by hand", "Baking"),
    KeyHelp("g", "Catch a golden cookie while one is on screen", "Baking"),
    KeyHelp("up, down", "Move the selection through the building list", "Shop"),
    KeyHelp("x", "Buy the selected building", "Shop"),
    KeyHelp("1 / 2 / 3 / 4", "Set the buy amount to 1, 10, 100, or max", "Shop"),
    KeyHelp("b", "Buy the best building you can afford", "Shop"),
    KeyHelp("u", "Buy the cheapest available upgrade", "Shop"),
    KeyHelp("click a row", "Buy that building", "Shop"),
    KeyHelp("s", "Statistics", "Screens"),
    KeyHelp("a", "Achievements, earned and still to earn", "Screens"),
    KeyHelp("p", "Ascend, trading the run for heavenly chips", "Screens"),
    KeyHelp(",", "Settings, export, import, and reset", "Screens"),
    KeyHelp("?", "This screen", "Screens"),
    KeyHelp("escape", "Close a screen", "Screens"),
    KeyHelp("q, ctrl+c", "Save and quit", "Screens"),
)
