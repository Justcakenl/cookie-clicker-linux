"""Long-session pacing, against the bands in docs/BALANCE.md §8.2.

Six simulated hours in about four seconds, because the engine takes elapsed time as an argument.
"""

from __future__ import annotations

import itertools

import pytest

from cookie.engine import prestige
from cookie.engine.content import CONTENT
from tests import simulation

MINUTE = 60.0
HOUR = 3_600.0

# milestone, target, lower bound, upper bound, all in seconds of time played.
BANDS = [
    ("first_cursor", 5.0, 1.0, 15.0),
    ("ten_cursors", 55.0, 30.0, 120.0),
    ("first_grandma", 90.0, 55.0, 200.0),
    ("baked_1e3", 2.0 * MINUTE, 1.2 * MINUTE, 5.0 * MINUTE),
    ("first_farm", 7.8 * MINUTE, 4.5 * MINUTE, 15.0 * MINUTE),
    ("first_mine", 25.6 * MINUTE, 15.0 * MINUTE, 45.0 * MINUTE),
    ("baked_1e6", 38.8 * MINUTE, 23.0 * MINUTE, 68.0 * MINUTE),
    ("first_factory", 49.3 * MINUTE, 29.0 * MINUTE, 85.0 * MINUTE),
    ("first_bank", 1.58 * HOUR, 0.95 * HOUR, 2.8 * HOUR),
    ("first_temple", 3.68 * HOUR, 2.2 * HOUR, 6.0 * HOUR),
    ("baked_1e9", 3.82 * HOUR, 2.3 * HOUR, 6.0 * HOUR),
]

TIER_ORDER = [
    "first_cursor",
    "first_grandma",
    "first_farm",
    "first_mine",
    "first_factory",
    "first_bank",
    "first_temple",
]


@pytest.fixture(scope="module")
def reference() -> simulation.RunResult:
    return simulation.run()


@pytest.mark.parametrize(("milestone", "target", "lower", "upper"), BANDS)
def test_milestone_lands_inside_its_band(
    reference: simulation.RunResult,
    milestone: str,
    target: float,
    lower: float,
    upper: float,
) -> None:
    actual = reference.at(milestone)
    assert actual is not None, f"{milestone} was never reached inside the run"
    assert lower <= actual <= upper, (
        f"{milestone}: target {target:.0f}s, band [{lower:.0f}s, {upper:.0f}s], got {actual:.0f}s"
    )


def test_tiers_are_unlocked_in_order(reference: simulation.RunResult) -> None:
    """The best-ratio purchase rule must never invert the progression."""
    times = [reference.at(name) for name in TIER_ORDER]
    assert all(time is not None for time in times)
    for earlier, later in itertools.pairwise(times):
        assert earlier is not None
        assert later is not None
        assert later > earlier


def test_five_tiers_are_open_within_the_first_hour(reference: simulation.RunResult) -> None:
    within = [name for name in TIER_ORDER if (at := reference.at(name)) is not None and at <= HOUR]
    assert len(within) >= 5


def test_the_first_chip_is_neither_early_nor_out_of_reach(
    reference: simulation.RunResult,
) -> None:
    first_chip = reference.at("first_chip")
    assert first_chip is not None
    assert first_chip <= 6.0 * HOUR
    assert first_chip > 2.0 * HOUR, "ascension became trivially early"
    assert prestige.chips_for(reference.state.all_time_cookies) >= 1


def test_golden_cookies_keep_spawning_and_are_all_caught(
    reference: simulation.RunResult,
) -> None:
    """One catch per spawn proves both the scheduler and the catch latency."""
    assert reference.state.golden_cookies_caught >= 60
    assert reference.state.golden_cookies_missed == 0


def test_achievements_sit_on_the_intended_curve(reference: simulation.RunResult) -> None:
    earned = len(reference.state.achievements_unlocked)
    assert earned >= 25, f"only {earned} of {len(CONTENT.achievements)} achievements in six hours"


def test_the_run_is_reproducible() -> None:
    """Every other number in this file is meaningless without this one."""
    first = simulation.run(limit=20.0 * MINUTE)
    second = simulation.run(limit=20.0 * MINUTE)
    assert first.milestones == second.milestones
    assert first.state.all_time_cookies == second.state.all_time_cookies
    assert first.state.golden_cookies_caught == second.state.golden_cookies_caught


def test_a_different_seed_moves_the_details_but_not_the_shape() -> None:
    """A balance curve that only works at one seed is not a balance curve."""
    other = simulation.run(seed=simulation.SEED + 1, limit=1.0 * HOUR)
    assert other.at("first_grandma") is not None
    grandma = other.at("first_grandma")
    assert grandma is not None
    assert 55.0 <= grandma <= 200.0
    assert other.at("first_factory") is not None
