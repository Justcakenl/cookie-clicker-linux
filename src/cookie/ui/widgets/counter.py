"""The header: cookie count, production rate, and any effect that is running."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static

from cookie.engine.numbers import format_duration, format_rate


class CounterPanel(Horizontal):
    """Owns the three header values. Nothing else writes them."""

    cookies: reactive[float] = reactive(0.0)
    rate: reactive[float] = reactive(0.0)
    event_label: reactive[str] = reactive("")
    event_remaining: reactive[float] = reactive(0.0)

    def __init__(self, formatter: Callable[[float], str]) -> None:
        super().__init__()
        self._formatter = formatter
        # Held rather than queried: these are written ten times a second, and a query that runs
        # before compose has reached the DOM is a race, not an error worth handling.
        self._cookies = Static(id="counter-cookies")
        self._rate = Static(id="counter-rate")
        self._event = Static(id="counter-event")

    def compose(self) -> ComposeResult:
        yield self._cookies
        yield self._rate
        yield self._event

    @property
    def cookies_label(self) -> Static:
        """Exposed so a test can read what the player actually sees."""
        return self._cookies

    def set_formatter(self, formatter: Callable[[float], str]) -> None:
        self._formatter = formatter
        self._render_values()

    def watch_cookies(self) -> None:
        self._render_values()

    def watch_rate(self) -> None:
        self._render_values()

    def watch_event_label(self) -> None:
        self._render_values()

    def watch_event_remaining(self) -> None:
        self._render_values()

    def _render_values(self) -> None:
        self._cookies.update(f"{self._formatter(self.cookies)} cookies")
        self._rate.update(f"  {format_rate(self.rate)}")
        event = ""
        if self.event_label:
            event = f"  {self.event_label} {format_duration(self.event_remaining)}"
        self._event.update(event)
