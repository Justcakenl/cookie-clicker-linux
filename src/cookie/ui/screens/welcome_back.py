"""What the player sees on resume: time away, what it earned, and any bad news about the save."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Button, Static

from cookie.engine.numbers import format_duration, format_rate
from cookie.engine.tick import OFFLINE_CAP, OFFLINE_RATE, OfflineReport
from cookie.persistence.store import LoadResult, LoadStatus
from cookie.ui.screens.base import CardScreen, ModalCard


class WelcomeBackScreen(CardScreen):
    """Also the screen that reports a damaged save, because the player must acknowledge that."""

    def __init__(self, *, load: LoadResult, offline: OfflineReport | None) -> None:
        super().__init__()
        self._load = load
        self._offline = offline

    def compose(self) -> ComposeResult:
        with ModalCard():
            yield Static(self._title(), classes="title")
            for line in self._lines():
                yield Static(line)
            if self._load.notes:
                yield Static("\nWhat happened", classes="row-label")
                for note in self._load.notes:
                    yield Static(f"  {note}", classes="bad")
            yield Button("Continue", id="continue", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#continue", Button).focus()

    def on_button_pressed(self) -> None:
        self.dismiss(None)

    def _title(self) -> str:
        match self._load.status:
            case LoadStatus.RECOVERED_FROM_BACKUP:
                return "Your save was damaged"
            case LoadStatus.CORRUPT_STARTED_FRESH:
                return "No readable save was found"
            case _:
                return "Welcome back"

    def _lines(self) -> list[str]:
        match self._load.status:
            case LoadStatus.RECOVERED_FROM_BACKUP:
                return [
                    f"A backup was loaded instead: {self._load.source}.",
                    "You may have lost the progress made since that backup was written.",
                ]
            case LoadStatus.CORRUPT_STARTED_FRESH:
                return [
                    "The damaged file has been kept, not deleted, in the save directory.",
                    "This game starts from nothing.",
                ]
            case _:
                return self._offline_lines()

    def _offline_lines(self) -> list[str]:
        report = self._offline
        if report is None:
            return ["Nothing happened while you were away."]
        rate = format_rate(report.cps_used)
        credited = (
            f"Your bakery ran at {rate}, credited at {OFFLINE_RATE:.0%} while the game was closed."
        )
        lines = [
            f"Away for {format_duration(report.wall_seconds)}.",
            credited,
            f"That is {self.game.formatter(report.cookies_awarded)} cookies.",
        ]
        if report.capped:
            lines.append(
                "Offline earnings are capped at "
                f"{format_duration(OFFLINE_CAP)}, so the time beyond that was not counted."
            )
        return lines
