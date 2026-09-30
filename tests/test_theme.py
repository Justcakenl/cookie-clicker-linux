"""Palettes, the terminal theme, and how `system` decides which one to use."""

from __future__ import annotations

import pytest

from cookie.engine.state import Theme
from cookie.persistence.codec import _THEMES
from cookie.ui import theme


@pytest.mark.parametrize("name", theme.THEME_NAMES)
def test_every_offered_theme_produces_a_full_stylesheet(name: Theme) -> None:
    css = theme.stylesheet(name)
    assert "$" not in css, f"{name} left a token unsubstituted"
    assert "Screen {" in css
    assert "BuildingRow" in css


def test_every_palette_defines_the_same_tokens() -> None:
    """A missing token would leave a literal `$name` in the CSS and Textual would reject it."""
    palettes = {name: set(tokens) for name, tokens in theme._TOKENS.items()}
    reference = palettes["classic"]
    for name, tokens in palettes.items():
        assert tokens == reference, f"{name} differs: {tokens ^ reference}"


def test_every_offered_theme_is_accepted_by_the_save_format() -> None:
    """A theme the settings screen can set but the codec rejects would break the next load."""
    for name in theme.THEME_NAMES:
        assert name in _THEMES


def test_the_night_theme_is_dark_blue() -> None:
    tokens = theme._TOKENS["night"]
    red, green, blue = (int(tokens["bg"][index : index + 2], 16) for index in (1, 3, 5))
    assert blue > red
    assert blue > green
    assert red + green + blue < 160, "a night theme should be dark"


def test_the_day_theme_is_light() -> None:
    tokens = theme._TOKENS["day"]
    red, green, blue = (int(tokens["bg"][index : index + 2], 16) for index in (1, 3, 5))
    assert red + green + blue > 600


def test_the_terminal_theme_names_only_ansi_colours() -> None:
    for token, value in theme._TOKENS["terminal"].items():
        assert value.startswith("ansi_"), f"{token} is {value}, not a terminal colour"


def test_the_terminal_theme_is_the_only_one_using_the_terminal_palette() -> None:
    assert theme.uses_terminal_palette("terminal")
    for name in theme.THEME_NAMES:
        if name != "terminal":
            assert not theme.uses_terminal_palette(name)


@pytest.mark.parametrize(
    ("colorfgbg", "expected"),
    [
        ("15;0", "night"),
        ("0;15", "day"),
        ("0;7", "day"),
        ("15;default", "night"),
        ("", "night"),
        ("nonsense", "night"),
    ],
)
def test_system_follows_the_terminal_background(
    monkeypatch: pytest.MonkeyPatch, colorfgbg: str, expected: Theme
) -> None:
    monkeypatch.setenv("COLORFGBG", colorfgbg)
    assert theme.resolve("system") == expected


def test_system_falls_back_to_dark_when_the_terminal_says_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Most terminals never set COLORFGBG, and there is no portable way to ask."""
    monkeypatch.delenv("COLORFGBG", raising=False)
    assert not theme.terminal_prefers_light()
    assert theme.resolve("system") == "night"


def test_a_named_theme_resolves_to_itself() -> None:
    for name in theme.THEME_NAMES:
        if name != "system":
            assert theme.resolve(name) == name


def test_the_two_cookies_differ_in_height() -> None:
    assert theme.cookie_art(compact=True).count("\n") < theme.cookie_art(compact=False).count("\n")
