"""Settings, plus export, import, and the way in to a hard reset."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Input, RadioButton, RadioSet, Static, Switch

from cookie.engine.state import NumberFormat, Theme
from cookie.persistence import paths
from cookie.persistence.codec import DecodeError
from cookie.persistence.store import SaveError
from cookie.ui.screens.base import CardScreen, ModalCard
from cookie.ui.screens.reset import HardResetScreen
from cookie.ui.theme import THEME_NAMES

_NUMBER_FORMATS: tuple[tuple[NumberFormat, str], ...] = (
    ("short", "Short scale (1.23 million)"),
    ("scientific", "Scientific (1.235e+06)"),
    ("raw", "Every digit (1,234,567)"),
)

_THEME_LABELS: dict[Theme, str] = {
    "classic": "Classic, warm browns",
    "night": "Night, dark blue",
    "terminal": "Terminal, your own colours",
    "system": "System, light or dark from the terminal",
    "mono": "Monochrome",
    "high_contrast": "High contrast",
    "day": "Day, light",
}

_THEMES: tuple[tuple[Theme, str], ...] = tuple((name, _THEME_LABELS[name]) for name in THEME_NAMES)


def _number_format(name: str) -> NumberFormat | None:
    return next((value for value, _ in _NUMBER_FORMATS if value == name), None)


def _theme(name: str) -> Theme | None:
    return next((value for value, _ in _THEMES if value == name), None)


class SettingsScreen(CardScreen):
    def compose(self) -> ComposeResult:
        settings = self.game.session.state.settings
        with ModalCard(), VerticalScroll():
            yield Static("Settings", classes="title")

            yield Static("Number format", classes="row-label")
            with RadioSet(id="number-format"):
                for format_value, format_label in _NUMBER_FORMATS:
                    yield RadioButton(
                        format_label,
                        value=format_value == settings.number_format,
                        name=format_value,
                    )

            yield Static("\nTheme", classes="row-label")
            with RadioSet(id="theme"):
                for theme_value, theme_label in _THEMES:
                    yield RadioButton(
                        theme_label, value=theme_value == settings.theme, name=theme_value
                    )

            yield Static("\nDisplay", classes="row-label")
            with Horizontal():
                yield Switch(value=settings.animations, id="animations")
                yield Static("  Click animations")
            with Horizontal():
                yield Switch(value=settings.show_flavor, id="show-flavor")
                yield Static("  Flavor text in tooltips")

            yield Static("\nSave", classes="row-label")
            yield Static(f"  {self.game.session.store.save_path}", classes="hint")
            with Horizontal():
                yield Button("Export", id="export")
                yield Button("Import", id="import")
                yield Button("Hard reset", id="reset", variant="error")
            yield Input(placeholder="path to import from", id="import-path")
            yield Static("", id="save-status")

            yield Button("Close", id="close", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#close", Button).focus()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        chosen = event.pressed.name
        if chosen is None:
            return
        settings = self.game.session.state.settings
        if event.radio_set.id == "number-format":
            chosen_format = _number_format(chosen)
            if chosen_format is not None:
                settings.number_format = chosen_format
        elif event.radio_set.id == "theme":
            chosen_theme = _theme(chosen)
            if chosen_theme is not None:
                settings.theme = chosen_theme
        self.game.apply_settings_change()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        settings = self.game.session.state.settings
        if event.switch.id == "animations":
            settings.animations = event.value
        elif event.switch.id == "show-flavor":
            settings.show_flavor = event.value
        self.game.apply_settings_change()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "close":
                self.dismiss(None)
            case "export":
                self._export()
            case "import":
                self._import()
            case "reset":
                self.dismiss(None)
                self.game.push_screen(HardResetScreen())

    def _status(self, message: str, *, bad: bool = False) -> None:
        status = self.query_one("#save-status", Static)
        status.set_class(bad, "bad")
        status.set_class(not bad, "good")
        status.update(message)

    def _export(self) -> None:
        session = self.game.session
        destination = Path.cwd() / paths.export_name(now=session.wall_now())
        try:
            written = session.store.export_to(destination, session.state)
        except SaveError as error:
            self._status(str(error), bad=True)
            return
        self._status(f"Exported to {written}")

    def _import(self) -> None:
        raw = self.query_one("#import-path", Input).value.strip()
        if not raw:
            self._status("Give a path to import from.", bad=True)
            return
        session = self.game.session
        try:
            result = session.store.import_from(Path(raw).expanduser(), now=session.wall_now())
        except (DecodeError, SaveError, OSError) as error:
            self._status(str(error), bad=True)
            return
        session.adopt(result.state)
        self._status("Imported. The save it replaced is in backup 1.")
        self.game.replace_state("Save imported.")
