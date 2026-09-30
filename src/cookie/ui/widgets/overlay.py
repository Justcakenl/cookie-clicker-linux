"""Overlays: the golden cookie and the achievement toasts."""

from __future__ import annotations

from typing import Final

from textual import events
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static

TOAST_LIFETIME: Final[float] = 3.0
MAX_TOASTS: Final[int] = 3


class GoldenCookie(Static):
    """A floating prompt while a golden cookie is on screen. Click it or press the catch key."""

    class Caught(Message):
        """The player caught the cookie, by click or by key."""

    def __init__(self) -> None:
        super().__init__()
        self._remaining = 0.0

    def show(self, remaining: float) -> None:
        self._remaining = remaining
        self.add_class("visible")
        self._update_text()

    def hide(self) -> None:
        self._remaining = 0.0
        self.remove_class("visible")
        self.update("")

    def set_remaining(self, remaining: float) -> None:
        self._remaining = remaining
        if self.has_class("visible"):
            self._update_text()

    @property
    def is_showing(self) -> bool:
        return self.has_class("visible")

    def _update_text(self) -> None:
        self.update(f"Golden cookie!\n[g] catch  {self._remaining:.0f}s")

    def on_click(self, event: events.Click) -> None:
        event.stop()
        if self.is_showing:
            self.post_message(self.Caught())


class Toast(Static):
    """One notification, alive for a few seconds."""

    def __init__(self, title: str, detail: str) -> None:
        super().__init__(f"{title}\n{detail}")
        self.remaining = TOAST_LIFETIME


class ToastStack(Vertical):
    """At most three toasts, newest at the bottom, each expiring on its own clock."""

    def push(self, title: str, detail: str) -> None:
        toasts = self.toasts
        while len(toasts) >= MAX_TOASTS:
            oldest = toasts.pop(0)
            oldest.remove()
        toast = Toast(title, detail)
        self.mount(toast)

    @property
    def toasts(self) -> list[Toast]:
        return list(self.query(Toast))

    def step(self, delta: float) -> None:
        for toast in self.toasts:
            toast.remaining -= delta
            if toast.remaining <= 0.0:
                toast.remove()
