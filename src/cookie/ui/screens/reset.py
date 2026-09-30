"""Hard reset, behind two confirmations of different kinds.

The two stages differ on purpose: a dialog with No focused, then a typed word. A double keypress
cannot pass both, which is the whole point of asking twice.
"""

from __future__ import annotations

from typing import Final

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Input, Static

from cookie.engine.actions import hard_reset
from cookie.ui.screens.base import CardScreen, ModalCard

CONFIRM_WORD: Final[str] = "RESET"


class HardResetScreen(CardScreen):
    def __init__(self) -> None:
        super().__init__()
        self._stage = 1

    def compose(self) -> ComposeResult:
        with ModalCard():
            yield Static("Delete everything", classes="title")
            yield Static(
                "This clears cookies, buildings, upgrades, achievements, heavenly chips,\n"
                "and every statistic. Your settings are kept.",
                classes="bad",
            )
            yield Static(
                "The save being replaced is rotated into backup 1, so it is still on disk.",
                classes="hint",
            )
            yield Static("", id="prompt")
            yield Input(placeholder=f"type {CONFIRM_WORD}", id="word", disabled=True)
            with Horizontal():
                yield Button("Keep playing", id="cancel", variant="primary")
                yield Button("Reset", id="confirm", variant="error")

    def on_mount(self) -> None:
        # The field is disabled rather than hidden. Showing it later would add a row and move the
        # buttons out from under the pointer between the two confirmations.
        self.query_one("#prompt", Static).update("Are you sure?")
        self.query_one("#cancel", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if self._stage == 1:
            self._stage = 2
            self.query_one("#prompt", Static).update(f"Type {CONFIRM_WORD} to confirm.")
            field = self.query_one("#word", Input)
            field.disabled = False
            field.focus()
            return
        self._perform_reset()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._perform_reset()

    def _perform_reset(self) -> None:
        if self.query_one("#word", Input).value.strip() != CONFIRM_WORD:
            self.query_one("#prompt", Static).update(
                f"That is not {CONFIRM_WORD}. Nothing has been deleted."
            )
            return
        session = self.game.session
        session.save()
        fresh = hard_reset(session.state, now=session.wall_now())
        session.adopt(fresh)
        self.dismiss(None)
        self.game.replace_state("Everything is gone. Good luck.")
