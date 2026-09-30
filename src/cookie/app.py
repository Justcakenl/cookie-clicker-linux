"""The Textual application: wiring, timers, and the shutdown path.

The engine and the renderer run on separate cadences. The engine is driven by real elapsed time,
so a stalled event loop costs a frame and never a cookie; the UI refreshes at its own rate and
reads only values the app hands it.
"""

from __future__ import annotations

import asyncio
import atexit
import signal
from collections.abc import Callable
from typing import ClassVar, Final

from textual.app import App
from textual.binding import BindingType

from cookie import __version__
from cookie.engine import numbers
from cookie.engine.actions import (
    BuyAmount,
    buy_building,
    buy_upgrade,
    catch_golden,
    click,
    resolve_buy_count,
)
from cookie.engine.derive import derive
from cookie.engine.errors import EngineError
from cookie.engine.state import GoldenPhase
from cookie.engine.tick import TickResult
from cookie.engine.unlocks import available_upgrades
from cookie.persistence.store import LoadStatus
from cookie.session import GameSession, ShutdownReason
from cookie.ui import present
from cookie.ui.keys import APP_BINDINGS
from cookie.ui.screens.achievements import AchievementsScreen
from cookie.ui.screens.help import HelpScreen
from cookie.ui.screens.main import MainScreen
from cookie.ui.screens.prestige import PrestigeScreen
from cookie.ui.screens.reset import HardResetScreen
from cookie.ui.screens.settings import SettingsScreen
from cookie.ui.screens.stats import StatsScreen
from cookie.ui.screens.too_small import TooSmallScreen
from cookie.ui.screens.welcome_back import WelcomeBackScreen
from cookie.ui.theme import MIN_HEIGHT, MIN_WIDTH, stylesheet, uses_terminal_palette

ENGINE_INTERVAL: Final[float] = 0.1
HEADER_INTERVAL: Final[float] = 0.1
SHOP_INTERVAL: Final[float] = 0.25
ANIMATION_INTERVAL: Final[float] = 0.05
AUTOSAVE_CHECK_INTERVAL: Final[float] = 1.0

# A terminal has no key-up event, so a held key arrives as a stream of ordinary presses, typically
# 25 to 33 a second. A person cannot tap faster than roughly eleven a second, so a gap shorter than
# this is the terminal repeating rather than the player pressing. A suppressed press still moves the
# marker forward, which is what makes a held key bake once rather than bake slowly: the run stays
# suppressed until a gap long enough to be a real press appears, meaning the key was released. The
# mouse has no key repeat, so clicks are not guarded.
KEY_REPEAT_GUARD: Final[float] = 0.09

_SIGNALS: Final[tuple[signal.Signals, ...]] = (
    signal.SIGINT,
    signal.SIGTERM,
    signal.SIGHUP,
)


class CookieApp(App[None]):
    """Owns the session, the timers, and the signal handlers."""

    TITLE = "Cookie"
    CSS = stylesheet("classic")
    # The palette would offer a second, competing way to change the theme, and it costs a dozen
    # columns of footer that an 80-column terminal does not have to spare.
    ENABLE_COMMAND_PALETTE = False
    # Textual's text selection turns a click into a drag-select: the widget highlights and the app
    # reports a copy. In a game where clicking means "bake a cookie", that is the wrong reading of
    # every click. Anyone who wants the numbers as text has `cookie --stats`, which prints them to
    # the terminal where the terminal's own selection works.
    ALLOW_SELECT = False
    BINDINGS: ClassVar[list[BindingType]] = list(APP_BINDINGS)

    def __init__(self, session: GameSession) -> None:
        super().__init__()
        self.session = session
        self._main = MainScreen(session.content, numbers.formatter_for("short"))
        self._too_small = False
        self._atexit_registered = False
        self._last_key_bake = float("-inf")

    @property
    def formatter(self) -> Callable[[float], str]:
        return numbers.formatter_for(self.session.state.settings.number_format)

    @property
    def main(self) -> MainScreen:
        """The game screen, held by reference rather than looked up by name."""
        return self._main

    def on_mount(self) -> None:
        report = self.session.start()
        self.stylesheet_for_theme()
        self.push_screen(self._main)
        self._install_signal_handlers()
        self._register_atexit()

        self.set_interval(ENGINE_INTERVAL, self._engine_tick)
        self.set_interval(HEADER_INTERVAL, self._refresh_header)
        self.set_interval(SHOP_INTERVAL, self.refresh_shop)
        self.set_interval(ANIMATION_INTERVAL, self._animation_tick)
        self.set_interval(AUTOSAVE_CHECK_INTERVAL, self._autosave)

        if report.load.needs_acknowledgement:
            self.push_screen(WelcomeBackScreen(load=report.load, offline=None))
        elif report.offline is not None:
            self.push_screen(WelcomeBackScreen(load=report.load, offline=report.offline))
        elif report.load.status is LoadStatus.OK:
            self.notify_line("Welcome back.")

    def stylesheet_for_theme(self) -> None:
        """Re-apply the stylesheet after a theme change."""
        theme = self.session.state.settings.theme
        # The terminal theme names ANSI colours, which Textual only passes through to the terminal
        # unchanged when it is told not to convert them to RGB.
        self.ansi_color = uses_terminal_palette(theme)
        self.app.stylesheet.add_source(stylesheet(theme), read_from=None)
        self.app.stylesheet.parse()
        self.refresh_css()

    def _register_atexit(self) -> None:
        if self._atexit_registered:
            return
        atexit.register(self._on_atexit)
        self._atexit_registered = True

    def _install_signal_handlers(self) -> None:
        """Signals go through the event loop, so the handler may touch state safely.

        Ctrl+C in a terminal arrives as a key event rather than SIGINT, because Textual puts the
        terminal in raw mode; it is bound to the same quit action. These handlers cover a signal
        sent from outside, including SIGHUP when the terminal closes.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        for received in _SIGNALS:
            try:
                loop.add_signal_handler(received, self._on_signal, received)
            except (NotImplementedError, RuntimeError, ValueError):
                # Non-Unix, or a loop that will not take handlers. Arch is the target; the key
                # binding and the atexit hook still cover quitting.
                return

    def _on_signal(self, received: signal.Signals) -> None:
        if self.session.shutting_down and received is signal.SIGINT:
            # A second Ctrl+C means the player wants out more than they want another save attempt.
            raise SystemExit(130)
        self.session.shutdown(ShutdownReason.SIGNAL)
        self.exit(return_code=130)

    def _on_atexit(self) -> None:
        """A last-ditch save if the process leaves by a route Textual does not own."""
        if self.session.started:
            self.session.shutdown(ShutdownReason.ATEXIT)

    async def action_quit(self) -> None:
        """Bound to both q and ctrl+c, so either one saves before the process goes away."""
        self.session.shutdown(ShutdownReason.QUIT)
        self.exit()

    def _engine_tick(self) -> None:
        result = self.session.tick()
        self._drain(result)

    def _drain(self, result: TickResult) -> None:
        state = self.session.state
        content = self.session.content
        screen = self._main_if_active()
        if screen is None:
            return

        for achievement_id in result.new_achievements:
            achievement = content.achievement_by_id.get(achievement_id)
            if achievement is not None:
                screen.toasts.push(f"Achievement: {achievement.name}", achievement.description)
        for building_id in result.newly_revealed_buildings:
            building = content.building_by_id.get(building_id)
            if building is not None:
                screen.toasts.push("Unlocked", f"{building.name} is now in the shop.")

        golden = screen.golden
        if state.golden_phase is GoldenPhase.VISIBLE:
            remaining = max(0.0, state.golden_visible_until - state.time_played)
            if golden.is_showing:
                golden.set_remaining(remaining)
            else:
                golden.show(remaining)
        elif golden.is_showing:
            golden.hide()

        if result.golden_expired:
            screen.toasts.push("Missed", "A golden cookie went stale.")

    def _main_if_active(self) -> MainScreen | None:
        """The game screen, or None while it is not mounted."""
        if not self.session.started:
            return None
        screen = self._main
        # `ready` is set in the screen's on_mount and cleared on unmount, which is exactly the
        # window in which its widgets are usable.
        return screen if screen.ready else None

    def _refresh_header(self) -> None:
        self._check_size()
        screen = self._main_if_active()
        if screen is None:
            return
        state = self.session.state
        snapshot = derive(state, self.session.content)
        counter = screen.counter
        counter.cookies = state.cookies
        counter.rate = snapshot.cps
        label, remaining = present.active_event(state)
        counter.event_label = label
        counter.event_remaining = remaining

    def refresh_shop(self) -> None:
        screen = self._main_if_active()
        if screen is None:
            return
        state = self.session.state
        content = self.session.content
        screen.buildings.apply(present.building_rows(state, content, screen.buy_amount))
        # The upgrade bar is part of the shop. Painting it from the engine tick instead left
        # it a frame behind whatever had just been bought.
        screen.upgrades.apply(present.upgrade_entries(content, available_upgrades(state, content)))
        screen.news.update_for(state, content)

    def refresh_all(self) -> None:
        self._refresh_header()
        self.refresh_shop()

    def _animation_tick(self) -> None:
        screen = self._main_if_active()
        if screen is None:
            return
        screen.toasts.step(ANIMATION_INTERVAL)
        if self.session.state.settings.animations:
            screen.cookie.animate_pops(ANIMATION_INTERVAL)
        else:
            screen.cookie.clear_pops()

    def _autosave(self) -> None:
        if self.session.autosave() is False:
            self.notify_line(f"Could not save: {self.session.save_failure}")

    def _check_size(self) -> None:
        """Push or pop the too-small screen.

        Checked on the header timer rather than from a resize event: the App itself does not receive
        Resize, and polling a size ten times a second costs nothing.
        """
        too_small = self.size.width < MIN_WIDTH or self.size.height < MIN_HEIGHT
        if too_small == self._too_small:
            return
        self._too_small = too_small
        if too_small:
            self.push_screen(TooSmallScreen())
        elif isinstance(self.screen, TooSmallScreen):
            self.pop_screen()

    def bake(self, *, from_key: bool = False) -> None:
        """Bake one cookie. A keypress that arrives at key-repeat speed is ignored."""
        if from_key:
            now = self.session.monotonic_now()
            held = now - self._last_key_bake < KEY_REPEAT_GUARD
            self._last_key_bake = now
            if held:
                return
        result = click(self.session.state, self.session.content)
        screen = self._main_if_active()
        if screen is not None:
            screen.show_click(result.cookies_gained)
        self._drain_delta(result.delta.new_achievements)

    def catch_golden(self) -> None:
        caught = catch_golden(self.session.state, self.session.content)
        screen = self._main_if_active()
        if caught is None:
            if screen is not None:
                screen.report("No golden cookie right now.")
            return
        if screen is not None:
            screen.toasts.push("Golden cookie", caught.message)
            screen.golden.hide()
        self._drain_delta(caught.delta.new_achievements)
        self.refresh_all()

    def buy_building(self, building_id: str, amount: BuyAmount) -> None:
        state = self.session.state
        content = self.session.content
        count = resolve_buy_count(state, content, building_id, amount)
        if count <= 0:
            self.notify_line("Not enough cookies for that yet.")
            return
        try:
            result = buy_building(state, content, building_id, count)
        except EngineError as error:
            self._report_error(error)
            return
        spec = content.building_by_id[building_id]
        self.notify_line(f"Bought {result.count} x {spec.name}.")
        self._drain_delta(result.delta.new_achievements)
        self.refresh_all()

    def buy_upgrade(self, upgrade_id: str) -> None:
        try:
            result = buy_upgrade(self.session.state, self.session.content, upgrade_id)
        except EngineError as error:
            self._report_error(error)
            return
        spec = self.session.content.upgrade_by_id[upgrade_id]
        self.notify_line(f"Bought {spec.name}.")
        self._drain_delta(result.delta.new_achievements)
        self.refresh_all()

    def _drain_delta(self, achievements: tuple[str, ...]) -> None:
        screen = self._main_if_active()
        if screen is None:
            return
        for achievement_id in achievements:
            spec = self.session.content.achievement_by_id.get(achievement_id)
            if spec is not None:
                screen.toasts.push(f"Achievement: {spec.name}", spec.description)

    def notify_line(self, message: str) -> None:
        screen = self._main_if_active()
        if screen is not None:
            screen.report(message)

    def _report_error(self, error: EngineError) -> None:
        screen = self._main_if_active()
        if screen is not None:
            screen.report_error(error)

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_stats(self) -> None:
        self.push_screen(StatsScreen())

    def action_achievements(self) -> None:
        self.push_screen(AchievementsScreen())

    def action_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def action_prestige(self) -> None:
        self.push_screen(PrestigeScreen())

    def action_hard_reset(self) -> None:
        self.push_screen(HardResetScreen())

    def apply_settings_change(self) -> None:
        """After a settings edit: re-theme, re-format, and save the preference immediately."""
        self.stylesheet_for_theme()
        screen = self._main_if_active()
        if screen is not None:
            screen.refresh_formatters()
        self.refresh_all()
        self.session.save()

    def replace_state(self, message: str) -> None:
        """After a prestige, an import, or a reset: refresh everything and save."""
        self.refresh_all()
        self.notify_line(message)
        self.session.save()


def build_app(session: GameSession) -> CookieApp:
    app = CookieApp(session)
    app.sub_title = __version__
    return app
