"""The real application, driven headless through Textual's pilot.

These tests press the real keys against the real screens. Anything that only checks a widget in
isolation belongs in a unit test; what is worth proving here is that the wiring holds.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from textual.pilot import Pilot
from textual.widgets import Input, RadioButton, RadioSet, Switch

from cookie.app import KEY_REPEAT_GUARD, CookieApp
from cookie.engine.content import CONTENT, ContentIndex
from cookie.engine.state import GoldenPhase
from cookie.engine.unlocks import evaluate_unlocks
from cookie.persistence.codec import payload_checksum
from cookie.persistence.store import SaveStore
from cookie.session import GameSession
from cookie.ui.keys import APP_BINDINGS, GAME_BINDINGS, HELP_ROWS
from cookie.ui.screens.achievements import EARNED, UNEARNED, AchievementsScreen
from cookie.ui.screens.help import HelpScreen
from cookie.ui.screens.main import MainScreen
from cookie.ui.screens.prestige import PrestigeScreen
from cookie.ui.screens.reset import HardResetScreen
from cookie.ui.screens.settings import SettingsScreen
from cookie.ui.screens.stats import StatsScreen
from cookie.ui.screens.too_small import TooSmallScreen
from cookie.ui.screens.welcome_back import WelcomeBackScreen
from cookie.ui.theme import THEME_NAMES
from cookie.ui.widgets.news import ROTATE_AFTER
from cookie.ui.widgets.shop import LOCKED_LABEL
from tests.conftest import SEED

DEFAULT_SIZE = (100, 30)
MINIMUM_SIZE = (80, 24)


async def eventually(
    pilot: Pilot[None], predicate: Callable[[], bool], *, timeout: float = 3.0
) -> None:
    """Pump the event loop until a condition holds.

    The interface is driven by timers at 4 to 20 Hz, so anything they paint arrives a frame or more
    after the state changes. Waiting for the condition is honest about that; a fixed sleep is a
    guess that gets shorter every time the suite grows.
    """
    deadline = time.monotonic() + timeout
    while True:
        await pilot.pause()
        if predicate():
            return
        if time.monotonic() >= deadline:
            raise AssertionError(f"condition still false after {timeout}s")


def text_of(widget: object) -> str:
    """The visible text of a Static, however Textual stores it this version."""
    content = getattr(widget, "content", None)
    return "" if content is None else str(content)


def make_app(tmp_path: Path, content: ContentIndex = CONTENT) -> CookieApp:
    store = SaveStore(tmp_path / "cookie", content=content, app_version="test")
    return CookieApp(GameSession(store, content=content, seed=SEED))


@pytest.fixture
def app(tmp_path: Path) -> CookieApp:
    return make_app(tmp_path)


async def test_the_game_boots_and_quits(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        assert isinstance(pilot.app.screen, MainScreen)
        await pilot.press("q")
    assert app.session.store.save_path.exists()


async def test_it_boots_at_the_documented_minimum_size(app: CookieApp) -> None:
    async with app.run_test(size=MINIMUM_SIZE) as pilot:
        assert isinstance(pilot.app.screen, MainScreen)
        assert not pilot.app.query(TooSmallScreen)


async def test_space_bakes_exactly_one_cookie(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.press("space")
        assert app.session.state.total_clicks == 1
        assert app.session.state.cookies == pytest.approx(1.0)


async def test_baking_shows_a_pop_and_respects_the_animation_setting(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        panel = app.main.cookie
        await pilot.press("space")
        assert panel.pop_count == 1

        app.session.state.settings.animations = False
        await pilot.press("space")
        await pilot.pause()
        assert panel.pop_count == 0
        assert app.session.state.total_clicks == 2


async def test_clicking_the_cookie_bakes(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.click("CookiePanel")
        assert app.session.state.total_clicks == 1


async def test_the_header_shows_cookies_and_the_rate(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        app.session.state.owned = {"grandma": 10}
        app.session.state.revision += 1
        await pilot.pause()
        app.refresh_all()
        counter = app.main.counter
        assert counter.rate == pytest.approx(10.0)


async def test_unrevealed_buildings_render_as_placeholders(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE):
        rows = app.main.buildings.rows
        assert len(rows) == len(CONTENT.buildings)
        assert rows[0].data is not None
        assert rows[0].data.revealed
        assert not rows[-1].data.revealed if rows[-1].data else False
        assert LOCKED_LABEL in text_of(rows[-1])


async def test_the_shop_row_count_never_changes_when_a_building_reveals(
    app: CookieApp,
) -> None:
    """A fixed row count is what keeps the list from jumping under the cursor."""
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        listing = app.main.buildings
        before = len(listing.rows)
        app.session.state.all_time_cookies = 1e9
        app.session.state.revision += 1
        app.refresh_shop()
        await pilot.pause()
        assert len(listing.rows) == before


async def test_buying_the_best_building_spends_cookies(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        app.session.state.cookies = 1_000.0
        app.session.state.revision += 1
        await pilot.press("b")
        assert app.session.state.owned
        assert app.session.state.cookies < 1_000.0


async def test_buying_with_nothing_reports_instead_of_raising(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.press("b")
        assert app.session.state.owned == {}
        assert app.main.toasts.toasts


async def test_the_buy_amount_keys_change_the_quoted_price(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        screen = app.main
        await pilot.press("2")
        chosen: object = screen.buy_amount
        assert chosen == 10
        await pilot.press("4")
        chosen = screen.buy_amount
        assert chosen == "max"
        await pilot.press("1")
        chosen = screen.buy_amount
        assert chosen == 1


async def test_buying_the_selected_building(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        app.session.state.cookies = 500.0
        app.session.state.revision += 1
        app.refresh_shop()
        await pilot.press("x")
        assert app.session.state.owned.get("cursor", 0) == 1


async def test_moving_the_selection(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        listing = app.main.buildings
        assert listing.selected == 0
        await pilot.press("down", "down")
        assert listing.selected == 2
        await pilot.press("up")
        assert listing.selected == 1


async def test_buying_an_upgrade_from_the_bar(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        state = app.session.state
        state.total_clicks = 10
        state.cookies = 10_000.0
        state.revision += 1

        bar = app.main.upgrades
        await eventually(pilot, lambda: bar.cheapest_id is not None)
        cheapest = bar.cheapest_id

        await pilot.press("u")
        assert cheapest in state.upgrades_owned


async def test_catching_a_golden_cookie(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        state = app.session.state
        state.owned = {"grandma": 20}
        state.golden_next_spawn_at = 0.0
        state.revision += 1
        await pilot.pause(0.3)

        assert state.golden_phase is GoldenPhase.VISIBLE
        assert app.main.golden.is_showing
        await pilot.press("g")
        assert state.golden_cookies_caught == 1
        assert not app.main.golden.is_showing


async def test_pressing_catch_with_nothing_there_reports(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.press("g")
        assert app.session.state.golden_cookies_caught == 0
        assert app.main.toasts.toasts


@pytest.mark.parametrize(
    ("key", "screen_type"),
    [
        ("question_mark", HelpScreen),
        ("s", StatsScreen),
        ("comma", SettingsScreen),
        ("p", PrestigeScreen),
    ],
)
async def test_every_screen_opens_and_closes(
    app: CookieApp, key: str, screen_type: type[object]
) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.press(key)
        assert isinstance(pilot.app.screen, screen_type)
        await pilot.press("escape")
        assert isinstance(pilot.app.screen, MainScreen)


async def test_the_help_screen_lists_every_shown_binding(app: CookieApp) -> None:
    """The footer and the help screen must not drift apart from the binding table."""
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.press("question_mark")
        rendered = " ".join(text_of(widget) for widget in pilot.app.screen.query("Static"))
        for row in HELP_ROWS:
            assert row.action in rendered
        for binding in GAME_BINDINGS:
            if binding.show:
                assert binding.key_display or binding.key


async def test_the_stats_screen_reports_what_happened(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        for _ in range(5):
            await pilot.press("space")
        await pilot.press("s")
        rendered = " ".join(text_of(widget) for widget in pilot.app.screen.query("Static"))
        assert "Clicks" in rendered
        assert "Time played" in rendered
        assert "Golden cookies caught" in rendered


async def test_the_prestige_screen_refuses_until_a_chip_is_earned(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.press("p")
        screen = pilot.app.screen
        assert isinstance(screen, PrestigeScreen)
        confirm = screen.query_one("#confirm")
        assert confirm.disabled

        await pilot.press("escape")
        app.session.state.all_time_cookies = 1e12
        app.session.state.revision += 1
        await pilot.press("p")
        assert not pilot.app.screen.query_one("#confirm").disabled


async def test_ascending_resets_the_run_and_keeps_the_record(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        state = app.session.state
        state.all_time_cookies = 1e12
        state.run_cookies = 1e12
        state.cookies = 1e11
        state.owned = {"grandma": 30}
        state.revision += 1

        await pilot.press("p")
        await pilot.click("#confirm")
        await pilot.pause()

        assert state.prestige_count == 1
        assert state.heavenly_chips == 10
        assert state.owned == {}
        assert state.all_time_cookies >= 1e12
        assert isinstance(pilot.app.screen, MainScreen)


async def test_a_hard_reset_needs_the_typed_word(app: CookieApp) -> None:
    """Two confirmations of different kinds: a button, and then the word typed into a field.

    The second stage is submitted with enter rather than a third click. Textual reads repeated
    clicks at one position as a click chain and delivers the later ones as a double click, which the
    button ignores; that is the right behaviour for a destructive dialog and the wrong way to drive
    it from a test.
    """
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        state = app.session.state
        state.all_time_cookies = 5_000.0
        state.run_cookies = 5_000.0
        state.revision += 1

        app.push_screen(HardResetScreen())
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, HardResetScreen)

        await pilot.click("#confirm")
        await pilot.pause()
        assert not screen.query_one("#word", Input).disabled

        await pilot.press("enter")
        await pilot.pause()
        assert app.session.state.all_time_cookies == 5_000.0
        assert "RESET" in text_of(screen.query_one("#prompt"))

        screen.query_one("#word", Input).value = "RESET"
        await pilot.press("enter")
        await pilot.pause()
        assert app.session.state.all_time_cookies == 0.0
        assert app.session.state.heavenly_chips == 0
        assert isinstance(pilot.app.screen, MainScreen)


async def test_cancelling_a_hard_reset_changes_nothing(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        state = app.session.state
        state.all_time_cookies = 5_000.0
        state.run_cookies = 5_000.0
        state.revision += 1

        app.push_screen(HardResetScreen())
        await pilot.pause()
        await pilot.click("#cancel")
        await pilot.pause()
        assert app.session.state.all_time_cookies == 5_000.0
        assert isinstance(pilot.app.screen, MainScreen)


async def test_changing_the_number_format_changes_what_the_header_shows(
    app: CookieApp,
) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        app.session.state.cookies = 1_234_567.0
        app.refresh_all()
        await pilot.pause()
        header = app.main.counter.cookies_label
        assert "million" in text_of(header)

        app.session.state.settings.number_format = "raw"
        app.apply_settings_change()
        await pilot.pause()
        assert "1,234,567" in text_of(header)


async def test_shrinking_below_the_minimum_shows_a_warning_and_keeps_ticking(
    app: CookieApp,
) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        app.session.state.owned = {"grandma": 10}
        app.session.state.revision += 1

        await pilot.resize_terminal(40, 10)
        await eventually(pilot, lambda: isinstance(pilot.app.screen, TooSmallScreen))

        before = app.session.state.all_time_cookies
        await eventually(pilot, lambda: app.session.state.all_time_cookies > before)

        await pilot.resize_terminal(*DEFAULT_SIZE)
        await eventually(pilot, lambda: isinstance(pilot.app.screen, MainScreen))


async def test_resizing_narrow_swaps_to_the_compact_cookie(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        art = app.main.cookie.art
        tall = text_of(art).count("\n")
        await pilot.resize_terminal(*MINIMUM_SIZE)
        await pilot.pause()
        assert text_of(art).count("\n") <= tall


async def test_quitting_saves_and_resuming_credits_time_away(tmp_path: Path) -> None:
    first = make_app(tmp_path)
    async with first.run_test(size=DEFAULT_SIZE) as pilot:
        first.session.state.owned = {"grandma": 10}
        first.session.state.revision += 1
        await pilot.press("q")
    assert first.session.store.save_path.exists()

    second = make_app(tmp_path)
    async with second.run_test(size=DEFAULT_SIZE) as pilot:
        assert second.session.state.owned == {"grandma": 10}
        await pilot.press("q")


async def test_a_recovered_save_is_acknowledged_before_play(tmp_path: Path) -> None:
    first = make_app(tmp_path)
    async with first.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.press("q")
    store = first.session.store
    store.save(first.session.state)
    store.save_path.write_text("wrecked", encoding="utf-8")

    second = make_app(tmp_path)
    async with second.run_test(size=DEFAULT_SIZE) as pilot:
        assert isinstance(pilot.app.screen, WelcomeBackScreen)
        await pilot.click("#continue")
        await pilot.pause()
        assert isinstance(pilot.app.screen, MainScreen)


async def test_the_settings_screen_exports_and_imports(
    app: CookieApp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        state = app.session.state
        state.all_time_cookies = 8_000.0
        state.run_cookies = 8_000.0
        state.owned = {"grandma": 3}
        state.revision += 1

        await pilot.press("comma")
        screen = pilot.app.screen
        assert isinstance(screen, SettingsScreen)
        await pilot.click("#export")
        await pilot.pause()
        exported = sorted(tmp_path.glob("cookie-save-*.json"))
        assert len(exported) == 1
        assert "Exported to" in text_of(screen.query_one("#save-status"))

        state.all_time_cookies = 1.0
        state.run_cookies = 1.0
        state.owned = {}
        state.revision += 1

        screen.query_one("#import-path", Input).value = str(exported[0])
        await pilot.click("#import")
        await pilot.pause()
        # At least: the bakery keeps running between the export and the import, so the restored
        # total is the exported one plus whatever the grandmas baked in between.
        assert app.session.state.all_time_cookies >= 8_000.0
        assert app.session.state.owned == {"grandma": 3}


async def test_importing_without_a_path_says_so(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.press("comma")
        screen = pilot.app.screen
        await pilot.click("#import")
        await pilot.pause()
        assert "Give a path" in text_of(screen.query_one("#save-status"))


async def test_importing_rubbish_reports_and_keeps_the_game(app: CookieApp, tmp_path: Path) -> None:
    junk = tmp_path / "junk.json"
    junk.write_text("not a save", encoding="utf-8")
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        app.session.state.all_time_cookies = 77.0
        app.session.state.run_cookies = 77.0
        app.session.state.revision += 1

        await pilot.press("comma")
        screen = pilot.app.screen
        screen.query_one("#import-path", Input).value = str(junk)
        await pilot.click("#import")
        await pilot.pause()
        assert "cannot import" in text_of(screen.query_one("#save-status"))
        assert app.session.state.all_time_cookies == 77.0


async def test_switching_theme_and_toggling_animations(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.press("comma")
        screen = pilot.app.screen
        assert isinstance(screen, SettingsScreen)

        theme_set = screen.query_one("#theme", RadioSet)
        night = next(b for b in theme_set.query(RadioButton) if b.name == "night")
        night.value = True
        await pilot.pause()
        assert app.session.state.settings.theme == "night"

        screen.query_one("#animations", Switch).value = False
        await pilot.pause()
        assert app.session.state.settings.animations is False

        format_set = screen.query_one("#number-format", RadioSet)
        format_set.query(RadioButton)[1].value = True
        await pilot.pause()
        assert app.session.state.settings.number_format == "scientific"


async def test_the_settings_screen_opens_the_hard_reset(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.press("comma")
        await pilot.click("#reset")
        await pilot.pause()
        assert isinstance(pilot.app.screen, HardResetScreen)


async def test_the_welcome_back_screen_reports_what_was_earned(tmp_path: Path) -> None:
    first = make_app(tmp_path)
    async with first.run_test(size=DEFAULT_SIZE) as pilot:
        first.session.state.owned = {"grandma": 20}
        first.session.state.revision += 1
        await pilot.press("q")

    store = first.session.store
    envelope = json.loads(store.save_path.read_text(encoding="utf-8"))
    envelope["saved_at"] = envelope["saved_at"] - 7_200.0
    envelope["checksum"] = payload_checksum(envelope["payload"])
    store.save_path.write_text(json.dumps(envelope), encoding="utf-8")

    second = make_app(tmp_path)
    async with second.run_test(size=DEFAULT_SIZE) as pilot:
        screen = pilot.app.screen
        assert isinstance(screen, WelcomeBackScreen)
        rendered = " ".join(text_of(widget) for widget in screen.query("Static"))
        assert "Welcome back" in rendered
        assert "Away for" in rendered
        assert "50%" in rendered
        assert second.session.state.cookies > 0.0
        await pilot.click("#continue")
        await pilot.pause()
        assert isinstance(pilot.app.screen, MainScreen)


async def test_the_welcome_back_screen_says_when_offline_time_was_capped(
    tmp_path: Path,
) -> None:
    first = make_app(tmp_path)
    async with first.run_test(size=DEFAULT_SIZE) as pilot:
        first.session.state.owned = {"grandma": 20}
        first.session.state.revision += 1
        await pilot.press("q")

    store = first.session.store
    envelope = json.loads(store.save_path.read_text(encoding="utf-8"))
    envelope["saved_at"] = envelope["saved_at"] - 5.0 * 86_400.0
    envelope["checksum"] = payload_checksum(envelope["payload"])
    store.save_path.write_text(json.dumps(envelope), encoding="utf-8")

    second = make_app(tmp_path)
    async with second.run_test(size=DEFAULT_SIZE) as pilot:
        rendered = " ".join(text_of(widget) for widget in pilot.app.screen.query("Static"))
        assert "capped" in rendered


def _fixed_gaps(app: CookieApp, monkeypatch: pytest.MonkeyPatch, gap: float) -> None:
    """Make every keypress arrive exactly `gap` seconds after the last, whatever the test costs."""
    ticks = iter(index * gap for index in range(1, 1_000))
    monkeypatch.setattr(app.session, "monotonic_now", lambda: next(ticks))


async def test_holding_the_bake_key_bakes_once(
    app: CookieApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A held key arrives as a stream of ordinary presses; a terminal sends no key-up event.

    At a typical 30 a second the gaps are far shorter than anyone can tap, so the whole run is one
    press. Before this, resting a finger on space baked cookies for as long as you left it there.
    """
    _fixed_gaps(app, monkeypatch, 1.0 / 30.0)
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        for _ in range(40):
            await pilot.press("space")
        assert app.session.state.total_clicks == 1


async def test_releasing_and_pressing_again_bakes_again(
    app: CookieApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    gaps = iter([0.0, 0.033, 0.033, 0.033, 0.5, 0.033, 0.033, 0.5])
    now = 0.0

    def clock() -> float:
        nonlocal now
        now += next(gaps)
        return now

    monkeypatch.setattr(app.session, "monotonic_now", clock)
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        for _ in range(8):
            await pilot.press("space")
        # Three runs of held key, three deliberate presses.
        assert app.session.state.total_clicks == 3


async def test_deliberate_tapping_still_counts_every_press(
    app: CookieApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard must not eat presses a person could actually make."""
    _fixed_gaps(app, monkeypatch, KEY_REPEAT_GUARD * 2)
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        for _ in range(10):
            await pilot.press("space")
        assert app.session.state.total_clicks == 10


async def test_clicking_the_cookie_is_never_guarded(app: CookieApp) -> None:
    """A mouse has no key repeat, so a fast click is a real click."""
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        for _ in range(6):
            await pilot.click("CookiePanel")
        assert app.session.state.total_clicks == 6


async def test_every_theme_can_be_applied_to_the_running_game(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        for name in THEME_NAMES:
            app.session.state.settings.theme = name
            app.apply_settings_change()
            await pilot.pause()
            assert app.session.state.settings.theme == name
            assert app.ansi_color == (name == "terminal")
        assert isinstance(pilot.app.screen, MainScreen)


async def test_a_theme_survives_a_restart(tmp_path: Path) -> None:
    first = make_app(tmp_path)
    async with first.run_test(size=DEFAULT_SIZE) as pilot:
        first.session.state.settings.theme = "night"
        first.apply_settings_change()
        await pilot.press("q")

    second = make_app(tmp_path)
    async with second.run_test(size=DEFAULT_SIZE) as pilot:
        assert second.session.state.settings.theme == "night"
        await pilot.press("q")


async def test_the_achievements_screen_shows_earned_and_unearned(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        state = app.session.state
        state.total_clicks = 10
        state.revision += 1
        evaluate_unlocks(state, app.session.content)

        await pilot.press("a")
        screen = pilot.app.screen
        assert isinstance(screen, AchievementsScreen)
        rendered = " ".join(text_of(widget) for widget in screen.query("Static"))
        assert "Achievements" in rendered
        assert f"of {len(CONTENT.achievements)}" in rendered
        assert f"{EARNED} Tentative" in rendered
        assert f"{UNEARNED} Grandma's boy" in rendered
        for line in (text_of(w) for w in screen.query("Static")):
            for row in line.splitlines():
                assert len(row) <= 66, f"row too wide for 80 columns: {row!r}"

        await pilot.press("escape")
        assert isinstance(pilot.app.screen, MainScreen)


async def test_the_achievements_screen_groups_every_achievement(app: CookieApp) -> None:
    """A group that catches nothing would hide content behind a heading nobody sees."""
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.press("a")
        rendered = " ".join(text_of(widget) for widget in pilot.app.screen.query("Static"))
        for spec in CONTENT.achievements:
            assert spec.name in rendered, spec.id


async def test_the_news_ticker_appears_and_changes(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        state = app.session.state
        state.owned = {spec.id: 5 for spec in CONTENT.buildings}
        state.revision += 1
        await eventually(pilot, lambda: bool(text_of(app.main.news)))
        first = text_of(app.main.news)

        state.time_played += ROTATE_AFTER * 3
        await eventually(pilot, lambda: text_of(app.main.news) != first)


async def test_the_shop_lists_every_building(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE):
        assert len(app.main.buildings.rows) == len(CONTENT.buildings) == 32


async def test_the_selection_moves_through_the_whole_list(app: CookieApp) -> None:
    """The arrow keys live on the list, because a scrolling container eats them first."""
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        listing = app.main.buildings
        await pilot.press("down", "down")
        assert listing.selected == 2
        await pilot.press("end")
        assert listing.selected == len(CONTENT.buildings) - 1
        await pilot.press("home")
        assert listing.selected == 0
        await pilot.press("up")
        assert listing.selected == 0


async def test_the_footer_fits_at_the_minimum_width(app: CookieApp) -> None:
    """Every shown binding has to be readable at 80 columns, quit included."""
    async with app.run_test(size=MINIMUM_SIZE) as pilot:
        await pilot.pause()
        shown = [binding for binding in (*GAME_BINDINGS, *APP_BINDINGS) if binding.show]
        width = sum(len(b.key_display or b.key) + len(b.description) + 3 for b in shown)
        assert width <= MINIMUM_SIZE[0], f"footer needs {width} columns"


async def test_dragging_over_the_game_selects_no_text(app: CookieApp) -> None:
    """Clicking means bake, not select.

    Textual's text selection reads a click-drag as a selection, highlights the widget and reports a
    copy, which is the wrong reading of every click in a clicker. The app turns it off, and this
    pins that: a drag across the cookie and the shop must leave the screen with no selection.
    """
    assert CookieApp.ALLOW_SELECT is False

    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.mouse_down("CookiePanel", offset=(2, 1))
        await pilot.hover("CookiePanel", offset=(20, 3))
        await pilot.mouse_up("CookiePanel", offset=(20, 3))
        await pilot.pause()

        # The selection lands on the inner Static that holds the drawing, which is why the check
        # is on the screen's selection map and on that widget rather than on the panel around it.
        assert pilot.app.screen.selections == {}
        assert app.main.cookie.art.text_selection is None


async def test_a_click_still_bakes_after_selection_is_disabled(app: CookieApp) -> None:
    async with app.run_test(size=DEFAULT_SIZE) as pilot:
        await pilot.click("CookiePanel")
        assert app.session.state.total_clicks == 1
