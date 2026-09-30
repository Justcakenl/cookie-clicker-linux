"""The game screen. Owns the bindings and turns them into engine actions."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar, Final, cast

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer

from cookie.engine.actions import BuyAmount
from cookie.engine.content import ContentIndex
from cookie.engine.errors import EngineError
from cookie.ui import present
from cookie.ui.keys import GAME_BINDINGS
from cookie.ui.widgets.cookie import CookiePanel, pop_text
from cookie.ui.widgets.counter import CounterPanel
from cookie.ui.widgets.news import NewsTicker
from cookie.ui.widgets.overlay import GoldenCookie, ToastStack
from cookie.ui.widgets.shop import BuildingList, BuildingRow, UpgradeBar

if TYPE_CHECKING:
    from cookie.app import CookieApp

BUY_AMOUNTS: Final[dict[str, BuyAmount]] = {"1": 1, "10": 10, "100": 100, "max": "max"}


class MainScreen(Screen[None]):
    BINDINGS: ClassVar[list[BindingType]] = list(GAME_BINDINGS)

    def __init__(self, content: ContentIndex, formatter: Callable[[float], str]) -> None:
        super().__init__()
        self.buy_amount: BuyAmount = 1
        # Children are built here and held by reference. The app's timers start before compose has
        # put anything in the DOM, and a timer that has to query for a widget that may not exist
        # yet is a race waiting to be rediscovered.
        self.counter = CounterPanel(formatter)
        self.cookie = CookiePanel()
        self.upgrades = UpgradeBar(formatter)
        self.news = NewsTicker()
        self.buildings = BuildingList(len(content.buildings), formatter)
        self.golden = GoldenCookie()
        self.toasts = ToastStack()
        self.ready = False

    @property
    def game(self) -> CookieApp:
        return cast("CookieApp", self.app)

    def compose(self) -> ComposeResult:
        with Container(id="game"):
            yield self.counter
            yield self.cookie
            yield self.upgrades
            yield self.news
            yield self.buildings
            yield Footer()
        yield self.golden
        yield self.toasts

    def on_mount(self) -> None:
        self.ready = True
        self.buildings.focus()
        self.game.refresh_all()

    def on_unmount(self) -> None:
        self.ready = False

    def refresh_formatters(self) -> None:
        formatter = self.game.formatter
        self.counter.set_formatter(formatter)
        self.upgrades.set_formatter(formatter)
        self.buildings.set_formatter(formatter)

    def action_bake(self) -> None:
        self.game.bake(from_key=True)

    def action_catch_golden(self) -> None:
        self.game.catch_golden()

    def action_buy_amount(self, amount: str) -> None:
        self.buy_amount = BUY_AMOUNTS[amount]
        self.game.refresh_shop()
        self.game.notify_line(f"Buying {amount} at a time.")

    def action_buy_selected(self) -> None:
        building_id = self.buildings.selected_id
        if building_id is not None:
            self.game.buy_building(building_id, self.buy_amount)

    def action_buy_best(self) -> None:
        session = self.game.session
        building_id = present.best_affordable_building(session.state, session.content)
        if building_id is None:
            self.game.notify_line("Nothing is affordable yet.")
            return
        self.game.buy_building(building_id, self.buy_amount)

    def action_buy_upgrade(self) -> None:
        upgrade_id = self.upgrades.cheapest_id
        if upgrade_id is None:
            self.game.notify_line("No upgrades available yet.")
            return
        self.game.buy_upgrade(upgrade_id)

    def on_cookie_panel_baked(self, message: CookiePanel.Baked) -> None:
        message.stop()
        self.game.bake()

    def on_golden_cookie_caught(self, message: GoldenCookie.Caught) -> None:
        message.stop()
        self.game.catch_golden()

    def on_building_row_picked(self, message: BuildingRow.Picked) -> None:
        message.stop()
        self.game.buy_building(message.building_id, self.buy_amount)

    def show_click(self, value: float) -> None:
        self.cookie.flash()
        if self.game.session.state.settings.animations:
            self.cookie.pop(pop_text(value, self.game.formatter))

    def report(self, message: str) -> None:
        self.toasts.push("Cookie", message)

    def report_error(self, error: EngineError) -> None:
        self.toasts.push("Not possible", str(error))
