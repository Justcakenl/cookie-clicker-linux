"""The statistics screen, rendered from engine.stats."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from cookie.engine import numbers, stats
from cookie.engine.stats import StatRow, ValueKind
from cookie.ui.screens.base import CardScreen, ModalCard


class StatsScreen(CardScreen):
    def compose(self) -> ComposeResult:
        session = self.game.session
        view = stats.build(session.state, session.content)
        formatter = self.game.formatter
        with ModalCard(), VerticalScroll():
            yield Static("Statistics", classes="title")
            for title, rows in view.sections:
                yield Static(f"\n{title}", classes="row-label")
                for row in rows:
                    yield Static(f"  {row.label:<30}{_render(row, formatter)}")

    def on_mount(self) -> None:
        self.query_one(VerticalScroll).focus()


def _render(row: StatRow, formatter: Callable[[float], str]) -> str:
    match row.kind:
        case ValueKind.RATE:
            return numbers.format_rate(row.value)
        case ValueKind.DURATION:
            return numbers.format_duration(row.value)
        case ValueKind.COUNT:
            return f"{int(row.value):,}"
        case ValueKind.MULTIPLIER:
            return f"x{row.value:.3f}"
        case ValueKind.COOKIES:
            return formatter(row.value)
