"""Colour tokens and the stylesheet for the whole app.

Every theme is built from the same token names, so a widget never names a colour directly. The
layout is sized for 80x24: header 3 rows, cookie 9, upgrades 3, news 1, shop the remainder,
footer 1.
"""

from __future__ import annotations

import os
from typing import Final

from cookie.engine.state import Theme

# Themes the settings screen offers, in the order it offers them.
THEME_NAMES: Final[tuple[Theme, ...]] = (
    "classic",
    "night",
    "terminal",
    "system",
    "mono",
    "high_contrast",
)

MIN_WIDTH: Final[int] = 60
MIN_HEIGHT: Final[int] = 16
COMFORTABLE_WIDTH: Final[int] = 70
COMFORTABLE_HEIGHT: Final[int] = 22

_TOKENS: Final[dict[Theme, dict[str, str]]] = {
    "classic": {
        "bg": "#1c1410",
        "panel": "#271c15",
        "line": "#3d2c20",
        "text": "#efe3d4",
        "dim": "#a08b76",
        "cookie": "#d9a05b",
        "accent": "#f0c070",
        "good": "#8fbf6f",
        "bad": "#cf6a5a",
        "gold": "#ffd75f",
    },
    "night": {
        "bg": "#0b1020",
        "panel": "#121a30",
        "line": "#24314f",
        "text": "#dbe4f5",
        "dim": "#7d8cae",
        "cookie": "#7fb0e8",
        "accent": "#8fd0ff",
        "good": "#7fd6a8",
        "bad": "#e87a8a",
        "gold": "#ffd98a",
    },
    "day": {
        "bg": "#f6f2ea",
        "panel": "#eae2d4",
        "line": "#c9bda8",
        "text": "#2a231c",
        "dim": "#6d6154",
        "cookie": "#9a6528",
        "accent": "#8a5a12",
        "good": "#3f7a3f",
        "bad": "#9c3030",
        "gold": "#a97a10",
    },
    # The terminal's own palette, so the game inherits whatever colour scheme the user already
    # chose. `ansi_default` is the terminal's default foreground or background, not a fixed colour.
    "terminal": {
        "bg": "ansi_default",
        "panel": "ansi_default",
        "line": "ansi_bright_black",
        "text": "ansi_default",
        "dim": "ansi_bright_black",
        "cookie": "ansi_yellow",
        "accent": "ansi_bright_yellow",
        "good": "ansi_green",
        "bad": "ansi_red",
        "gold": "ansi_bright_yellow",
    },
    "mono": {
        "bg": "#101010",
        "panel": "#1a1a1a",
        "line": "#333333",
        "text": "#e8e8e8",
        "dim": "#909090",
        "cookie": "#cfcfcf",
        "accent": "#ffffff",
        "good": "#cfcfcf",
        "bad": "#9a9a9a",
        "gold": "#ffffff",
    },
    "high_contrast": {
        "bg": "#000000",
        "panel": "#000000",
        "line": "#ffffff",
        "text": "#ffffff",
        "dim": "#c8c8c8",
        "cookie": "#ffd000",
        "accent": "#00ffff",
        "good": "#00ff00",
        "bad": "#ff4040",
        "gold": "#ffff00",
    },
}

_STYLESHEET: Final[str] = """
Screen {
    background: $bg;
    color: $text;
}

#game {
    layout: vertical;
    height: 100%;
}

CounterPanel {
    height: 3;
    background: $panel;
    border-bottom: solid $line;
    padding: 0 1;
}

#counter-cookies {
    width: auto;
    text-style: bold;
    color: $accent;
}

#counter-rate {
    width: auto;
    color: $dim;
}

#counter-event {
    width: 1fr;
    color: $gold;
    text-style: bold;
}

CookiePanel {
    height: 9;
    align: center middle;
    background: $bg;
}

#cookie-art {
    color: $cookie;
    text-align: center;
    width: 100%;
}

#cookie-art.pressed {
    color: $accent;
}

PopLabel {
    layer: overlay;
    color: $accent;
    text-style: bold;
    width: auto;
    height: 1;
}

UpgradeBar {
    height: 3;
    background: $panel;
    border-top: solid $line;
    border-bottom: solid $line;
    padding: 0 1;
}

#upgrade-line {
    color: $good;
}

#upgrade-line.none {
    color: $dim;
}

NewsTicker {
    height: 1;
    background: $bg;
    color: $dim;
    text-style: italic;
    padding: 0 1;
}

BuildingList {
    height: 1fr;
    background: $bg;
}

BuildingRow {
    height: 1;
    padding: 0 1;
}

BuildingRow.affordable {
    color: $text;
}

BuildingRow.unaffordable {
    color: $dim;
}

BuildingRow.locked {
    color: $line;
}

BuildingRow.selected {
    background: $panel;
    text-style: bold;
}

GoldenCookie {
    layer: overlay;
    width: 22;
    height: 3;
    background: $panel;
    border: round $gold;
    color: $gold;
    text-align: center;
    offset: 100vw 0;
}

GoldenCookie.visible {
    offset: -24 1;
}

ToastStack {
    layer: overlay;
    width: 40;
    height: auto;
    offset: -42 4;
}

Toast {
    width: 100%;
    height: 2;
    background: $panel;
    border-left: thick $good;
    color: $text;
    padding: 0 1;
    margin-bottom: 1;
}

ModalCard {
    width: 72;
    max-width: 100%;
    height: auto;
    max-height: 100%;
    background: $panel;
    border: round $line;
    padding: 1 2;
}

ModalCard > .title {
    text-style: bold;
    color: $accent;
    margin-bottom: 1;
}

ModalCard > .hint {
    color: $dim;
    margin-top: 1;
}

.row-label {
    color: $dim;
}

.good {
    color: $good;
}

.bad {
    color: $bad;
}

#too-small {
    align: center middle;
    color: $bad;
    text-align: center;
}

Input {
    background: $bg;
    border: round $line;
}

Button {
    background: $panel;
    border: round $line;
    color: $text;
}

Button:focus {
    border: round $accent;
}
"""


def terminal_prefers_light() -> bool:
    """Whether the terminal reports a light background.

    Read from `COLORFGBG`, which a terminal sets to "foreground;background" using ANSI colour
    numbers; 7 and 15 are the light backgrounds. Plenty of terminals never set it, and there is no
    portable way to ask, so an absent or unreadable value means dark. That is the ceiling of the
    `system` theme and the reason the other five exist.
    """
    raw = os.environ.get("COLORFGBG")
    if not raw:
        return False
    background = raw.rsplit(";", 1)[-1].strip()
    return background in {"7", "15"}


def resolve(theme: Theme) -> Theme:
    """The palette a theme name actually renders with."""
    if theme != "system":
        return theme
    return "day" if terminal_prefers_light() else "night"


def uses_terminal_palette(theme: Theme) -> bool:
    """Whether the theme draws from the terminal's ANSI colours rather than fixed ones."""
    return resolve(theme) == "terminal"


def stylesheet(theme: Theme) -> str:
    """The stylesheet with the chosen theme's tokens substituted in."""
    tokens = _TOKENS[resolve(theme)]
    css = _STYLESHEET
    # Longest first: a plain substring replace would let a future "$bg" eat the start of "$bg2".
    for token in sorted(tokens, key=len, reverse=True):
        css = css.replace(f"${token}", tokens[token])
    return css


def cookie_art(*, compact: bool) -> str:
    """The big cookie. The compact variant exists so the game stays usable at 80x24."""
    if compact:
        return "\n".join(
            (
                '   .-"""""-.   ',
                "  / o . o  \\  ",
                " |  .  o .  | ",
                "  \\ o . o  /  ",
                "   '-.....-'   ",
            )
        )
    return "\n".join(
        (
            '      .-"""""""""-.      ',
            "    .'  o     .   '.    ",
            "   /   .   o     o  \\   ",
            "  |  o    .   .      |  ",
            "  |     o     o   .  |  ",
            "   \\  .    o     .  /   ",
            "    '.   o    .   .'    ",
            "      '-.........-'     ",
        )
    )
