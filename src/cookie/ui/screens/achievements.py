"""The achievement list: what has been earned, what is still out there, and what it is worth."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from cookie.engine.content import ContentIndex
from cookie.engine.specs import AchievementSpec, UnlockMetric
from cookie.engine.state import GameState
from cookie.ui.screens.base import CardScreen, ModalCard

# Not square brackets: Textual reads those as markup and eats the marker.
EARNED = "(x)"
UNEARNED = "( )"

# The card is 72 columns wide with a border and padding, so a row has this much to work with at the
# 80-column minimum. Descriptions are truncated rather than wrapped, because a wrapped row
# continues at the card's left edge and reads as a separate achievement.
ROW_WIDTH = 64
NAME_WIDTH = 26

_GROUPS: tuple[tuple[str, frozenset[UnlockMetric]], ...] = (
    ("Baking", frozenset({UnlockMetric.ALL_TIME_COOKIES, UnlockMetric.RUN_COOKIES})),
    ("Buildings", frozenset({UnlockMetric.BUILDING_OWNED})),
    (
        "Scale",
        frozenset(
            {
                UnlockMetric.TOTAL_BUILDINGS,
                UnlockMetric.DISTINCT_BUILDINGS,
                UnlockMetric.CPS,
                UnlockMetric.UPGRADES_OWNED,
            }
        ),
    ),
    ("Hands on", frozenset({UnlockMetric.TOTAL_CLICKS, UnlockMetric.GOLDEN_CAUGHT})),
    (
        "The long game",
        frozenset(
            {
                UnlockMetric.PRESTIGE_COUNT,
                UnlockMetric.TIME_PLAYED,
                UnlockMetric.OFFLINE_COOKIES,
            }
        ),
    ),
)


def group_of(spec: AchievementSpec) -> str:
    for title, metrics in _GROUPS:
        if spec.unlock.metric in metrics:
            return title
    return "Other"


class AchievementsScreen(CardScreen):
    """Unearned rows show their name and how to get it: a checklist, not a spoiler-free mystery."""

    def compose(self) -> ComposeResult:
        session = self.game.session
        state = session.state
        content = session.content
        earned = len(state.achievements_unlocked)
        total = len(content.achievements)
        bonus = sum(
            spec.cps_bonus
            for spec in content.achievements
            if spec.id in state.achievements_unlocked
        )

        with ModalCard(), VerticalScroll():
            yield Static("Achievements", classes="title")
            yield Static(
                f"{earned} of {total}, worth x{1.0 + bonus:.2f} now, "
                f"x{1.0 + total * _bonus_each(content):.2f} for all of them."
            )
            for title, _metrics in _GROUPS:
                rows = [spec for spec in content.achievements if group_of(spec) == title]
                if not rows:
                    continue
                held = sum(1 for spec in rows if spec.id in state.achievements_unlocked)
                yield Static(f"\n{title}  ({held} of {len(rows)})", classes="row-label")
                for spec in rows:
                    yield Static(_line(spec, state), classes=_style(spec, state))

    def on_mount(self) -> None:
        self.query_one(VerticalScroll).focus()


def _bonus_each(content: ContentIndex) -> float:
    return content.achievements[0].cps_bonus if content.achievements else 0.0


def _line(spec: AchievementSpec, state: GameState) -> str:
    mark = EARNED if spec.id in state.achievements_unlocked else UNEARNED
    row = f"{mark} {spec.name:<{NAME_WIDTH}}{spec.description}"
    if len(row) > ROW_WIDTH:
        row = row[: ROW_WIDTH - 3].rstrip() + "..."
    return row


def _style(spec: AchievementSpec, state: GameState) -> str:
    return "good" if spec.id in state.achievements_unlocked else "row-label"
