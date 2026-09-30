"""Shown while the terminal is below the usable minimum. The game keeps running behind it."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static

from cookie.ui.theme import MIN_HEIGHT, MIN_WIDTH


class TooSmallScreen(ModalScreen[None]):
    """No close binding: it leaves on its own when the terminal grows back."""

    def compose(self) -> ComposeResult:
        yield Static(
            f"The window is too small.\nCookie needs at least {MIN_WIDTH} by {MIN_HEIGHT}.",
            id="too-small",
        )
