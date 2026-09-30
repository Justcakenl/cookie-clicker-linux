"""The big cookie, its click target, and the "+N" pops that rise off it."""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from textual import events
from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.widgets import Static

from cookie.ui.theme import COMFORTABLE_HEIGHT, COMFORTABLE_WIDTH, cookie_art

POP_LIFETIME: Final[float] = 0.9
POP_RISE: Final[int] = 3
MAX_POPS: Final[int] = 6
PRESS_FRAMES: Final[int] = 2

FULL_HEIGHT: Final[int] = 9
COMPACT_HEIGHT: Final[int] = 6


class PopLabel(Static):
    """One transient "+N" that rises and disappears."""

    def __init__(self, text: str, column: int) -> None:
        super().__init__(text)
        self.remaining = POP_LIFETIME
        self._column = column
        self._start_row = 0

    def place(self, row: int) -> None:
        self._start_row = row
        self.styles.offset = (self._column, row)

    def step(self, delta: float) -> bool:
        """Advance the animation. Returns False once the pop is finished."""
        self.remaining -= delta
        if self.remaining <= 0.0:
            return False
        progress = 1.0 - (self.remaining / POP_LIFETIME)
        self.styles.offset = (self._column, self._start_row - int(progress * POP_RISE))
        self.styles.opacity = max(0.0, 1.0 - progress)
        return True


class CookiePanel(Container):
    """The cookie. Clicking it, or pressing the bake key, asks the app to bake."""

    class Baked(Message):
        """The player clicked the cookie."""

    def __init__(self) -> None:
        super().__init__()
        self._pops: list[PopLabel] = []
        self._press_frames = 0
        self._compact = False
        self._art = Static(cookie_art(compact=False), id="cookie-art")

    def compose(self) -> ComposeResult:
        yield self._art

    def on_resize(self, event: events.Resize) -> None:
        """Swap to the compact cookie on a small terminal, and give the rows back to the shop.

        With thirty-two buildings the list is the part that suffers first, so a short terminal loses
        three rows of drawing rather than three rows of shop.
        """
        narrow = event.size.width < COMFORTABLE_WIDTH
        compact = narrow or self.screen.size.height < COMFORTABLE_HEIGHT
        if compact == self._compact:
            return
        self._compact = compact
        self._art.update(cookie_art(compact=compact))
        self.styles.height = COMPACT_HEIGHT if compact else FULL_HEIGHT

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(self.Baked())

    def flash(self) -> None:
        """Briefly highlight the cookie, so a click is visible even with pops disabled."""
        self._art.add_class("pressed")
        self._press_frames = PRESS_FRAMES

    def pop(self, text: str) -> None:
        """Start a "+N" animation. Oldest pops are dropped rather than queued."""
        while len(self._pops) >= MAX_POPS:
            self._retire(self._pops[0])
        column = (len(self._pops) * 5) % 20 - 10
        label = PopLabel(text, column)
        self._pops.append(label)
        self.mount(label)
        label.place(-2)

    def animate_pops(self, delta: float) -> None:
        for label in list(self._pops):
            if not label.step(delta):
                self._retire(label)
        if self._press_frames:
            self._press_frames -= 1
            if not self._press_frames:
                self._art.remove_class("pressed")

    def clear_pops(self) -> None:
        for label in list(self._pops):
            self._retire(label)

    def _retire(self, label: PopLabel) -> None:
        if label in self._pops:
            self._pops.remove(label)
        label.remove()

    @property
    def art(self) -> Static:
        """Exposed so a test can read which cookie is on screen."""
        return self._art

    @property
    def pop_count(self) -> int:
        return len(self._pops)


def pop_text(value: float, formatter: Callable[[float], str]) -> str:
    return f"+{formatter(value)}"
