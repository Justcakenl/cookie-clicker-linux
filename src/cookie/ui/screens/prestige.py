"""Ascension: what it gains, what it costs, and what it leaves alone."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Static

from cookie.engine.actions import do_prestige, prestige_preview
from cookie.engine.errors import EngineError
from cookie.ui.screens.base import CardScreen, ModalCard


class PrestigeScreen(CardScreen):
    def compose(self) -> ComposeResult:
        session = self.game.session
        preview = prestige_preview(session.state, session.content)
        fmt = self.game.formatter

        with ModalCard(), VerticalScroll():
            yield Static("Ascend", classes="title")

            yield Static("You gain", classes="row-label")
            yield Static(f"  Heavenly chips     {preview.chips_held} -> {preview.chips_available}")
            yield Static(
                f"  Production bonus   x{preview.multiplier_now:.2f} -> "
                f"x{preview.multiplier_after:.2f}"
                f"  ({_delta(preview.multiplier_now, preview.multiplier_after)})",
                classes="good",
            )

            yield Static("\nYou lose", classes="row-label")
            yield Static(f"  Cookies in bank    {fmt(preview.cookies_lost)}", classes="bad")
            yield Static(f"  Production         {fmt(preview.cps_lost)} per second", classes="bad")
            yield Static(f"  Upgrades owned     {preview.upgrades_lost}", classes="bad")
            for building_id, owned in sorted(preview.buildings_lost.items()):
                name = session.content.building_by_id[building_id].name
                yield Static(f"    {name:<16}{owned}", classes="bad")

            yield Static("\nYou keep", classes="row-label")
            yield Static(
                "  Cookies baked all time, achievements, statistics, heavenly chips,\n"
                "  ascension count, and every building you have unlocked."
            )

            if preview.is_worthwhile:
                yield Static(
                    "\nThe bonus applies from the first Cursor of the next run.", classes="hint"
                )
            else:
                yield Static(
                    f"\nNot yet: {fmt(preview.cookies_until_next_chip)} more cookies baked "
                    "all time earns your next chip.",
                    classes="hint",
                )

            with Horizontal():
                yield Button(
                    "Ascend",
                    id="confirm",
                    variant="warning",
                    disabled=not preview.is_worthwhile,
                )
                yield Button("Cancel", id="cancel", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#cancel", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "confirm":
            self.dismiss(None)
            return
        session = self.game.session
        try:
            do_prestige(session.state, session.content)
        except EngineError as error:
            self.game.notify_line(str(error))
            self.dismiss(None)
            return
        self.dismiss(None)
        self.game.replace_state(
            f"Ascended. You now hold {session.state.heavenly_chips} heavenly chips."
        )


def _delta(before: float, after: float) -> str:
    if before <= 0.0:
        return "new"
    return f"+{(after / before - 1.0) * 100:.0f}%"
