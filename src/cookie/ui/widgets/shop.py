"""The shop: twelve building rows and the available-upgrade line.

Rows are given plain values by the app. They never hold a GameState and never compute a price.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static

LOCKED_LABEL = "???"


@dataclasses.dataclass(frozen=True, slots=True)
class BuildingRowData:
    """Everything one row displays, computed by the app."""

    building_id: str
    name: str
    owned: int
    cost: float
    contribution: float
    share: float
    affordable: bool
    revealed: bool
    flavor: str


class BuildingRow(Static):
    """One building line. Renders as ??? until the building is revealed."""

    class Picked(Message):
        def __init__(self, building_id: str) -> None:
            super().__init__()
            self.building_id = building_id

    def __init__(self, index: int, formatter: Callable[[float], str]) -> None:
        super().__init__()
        self._index = index
        self._formatter = formatter
        self._data: BuildingRowData | None = None

    @property
    def data(self) -> BuildingRowData | None:
        return self._data

    def set_formatter(self, formatter: Callable[[float], str]) -> None:
        self._formatter = formatter
        if self._data is not None:
            self.apply(self._data, selected=self.has_class("selected"))

    def apply(self, data: BuildingRowData, *, selected: bool) -> None:
        self._data = data
        self.set_class(selected, "selected")
        self.set_class(not data.revealed, "locked")
        self.set_class(data.revealed and data.affordable, "affordable")
        self.set_class(data.revealed and not data.affordable, "unaffordable")
        if not data.revealed:
            self.update(f"{LOCKED_LABEL:<14}")
            self.tooltip = None
            return

        owned = f"{data.owned:>4}"
        cost = self._formatter(data.cost)
        rate = self._formatter(data.contribution)
        share = f"{data.share * 100:4.0f}%" if data.share > 0.0 else "    "
        self.update(f"{data.name:<14}{owned}  {cost:>16}  {rate:>14}/s {share}")
        self.tooltip = data.flavor

    def on_click(self, event: events.Click) -> None:
        event.stop()
        if self._data is not None and self._data.revealed:
            self.post_message(self.Picked(self._data.building_id))


class BuildingList(VerticalScroll):
    """Always every row, so a reveal never reflows the list.

    The arrow keys are bound here rather than on the screen because a VerticalScroll consumes them
    for scrolling and the screen never sees them. Moving the selection scrolls it into view, which
    is what makes a list of thirty-two navigable in eight visible rows.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", "Up", show=False),
        Binding("down", "move(1)", "Down", show=False),
        Binding("pageup", "move(-8)", "Page up", show=False),
        Binding("pagedown", "move(8)", "Page down", show=False),
        Binding("home", "jump(0)", "First", show=False),
        Binding("end", "jump(-1)", "Last", show=False),
    ]

    selected: reactive[int] = reactive(0)

    def __init__(self, count: int, formatter: Callable[[float], str]) -> None:
        super().__init__()
        self._count = count
        self._formatter = formatter
        # Built here rather than queried later: the rows exist before the first refresh, so nothing
        # downstream has to cope with a half-composed list.
        self._rows = [BuildingRow(index, formatter) for index in range(count)]
        self.can_focus = True

    def compose(self) -> ComposeResult:
        yield from self._rows

    @property
    def rows(self) -> list[BuildingRow]:
        return list(self._rows)

    def set_formatter(self, formatter: Callable[[float], str]) -> None:
        self._formatter = formatter
        for row in self.rows:
            row.set_formatter(formatter)

    def apply(self, data: list[BuildingRowData]) -> None:
        for index, (row, values) in enumerate(zip(self.rows, data, strict=True)):
            row.apply(values, selected=index == self.selected)

    def watch_selected(self) -> None:
        rows = self.rows
        for index, row in enumerate(rows):
            row.set_class(index == self.selected, "selected")
        if self.is_mounted and rows:
            self.scroll_to_widget(rows[self.selected], animate=False)

    def move(self, delta: int) -> None:
        self.selected = max(0, min(self._count - 1, self.selected + delta))

    def action_move(self, delta: int) -> None:
        self.move(delta)

    def action_jump(self, index: int) -> None:
        self.selected = self._count - 1 if index < 0 else min(index, self._count - 1)

    @property
    def selected_id(self) -> str | None:
        rows = self.rows
        if not rows:
            return None
        data = rows[self.selected].data
        return None if data is None else data.building_id


class UpgradeBar(Static):
    """A single line naming the upgrades the player can buy right now."""

    def __init__(self, formatter: Callable[[float], str]) -> None:
        super().__init__(id="upgrade-line")
        self._formatter = formatter
        self._entries: list[tuple[str, str, float]] = []

    def set_formatter(self, formatter: Callable[[float], str]) -> None:
        self._formatter = formatter
        self.apply(self._entries)

    def apply(self, entries: list[tuple[str, str, float]]) -> None:
        """`entries` is (upgrade id, name, cost), cheapest first."""
        self._entries = entries
        if not entries:
            self.add_class("none")
            self.update("No upgrades available yet.")
            return
        self.remove_class("none")
        shown = [f"{name} ({self._formatter(cost)})" for _, name, cost in entries[:3]]
        more = len(entries) - len(shown)
        text = "Upgrades: " + "   ".join(shown)
        if more > 0:
            text += f"   and {more} more"
        self.update(text)

    @property
    def cheapest_id(self) -> str | None:
        return self._entries[0][0] if self._entries else None
