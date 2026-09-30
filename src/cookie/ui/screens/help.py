"""The help screen, rendered from the one keybinding table."""

from __future__ import annotations

import itertools

from textual.app import ComposeResult
from textual.widgets import Static

from cookie.ui.keys import HELP_ROWS
from cookie.ui.screens.base import CardScreen, ModalCard


class HelpScreen(CardScreen):
    def compose(self) -> ComposeResult:
        with ModalCard():
            yield Static("Cookie", classes="title")
            yield Static(
                "Click the cookie, buy buildings, buy upgrades, catch golden cookies.\n"
                "Ascend when a run has earned heavenly chips, and the next one goes faster.",
            )
            for group, rows in itertools.groupby(HELP_ROWS, key=lambda row: row.group):
                yield Static(f"\n{group}", classes="row-label")
                for row in rows:
                    yield Static(f"  {row.keys:<18}{row.action}")
            yield Static("Progress saves every 30 seconds and on the way out.", classes="hint")
