"""Chip arithmetic, including the exact-cube boundaries, per docs/BALANCE.md §6."""

from __future__ import annotations

import pytest

from cookie.engine.prestige import (
    CHIP_DIVISOR,
    CHIP_MULTIPLIER,
    chips_for,
    cookies_for_chips,
    multiplier_for,
)

DOCUMENTED_TABLE = [
    (1e9, 1, 1.05),
    (8e9, 2, 1.10),
    (2.7e10, 3, 1.15),
    (6.4e10, 4, 1.20),
    (1e11, 4, 1.20),
    (1e12, 10, 1.50),
    (1e13, 21, 2.05),
    (1e14, 46, 3.30),
    (1e15, 100, 6.00),
    (1e18, 1_000, 51.00),
    (1e21, 10_000, 501.00),
    (1e24, 100_000, 5_001.00),
]


@pytest.mark.parametrize(("all_time", "chips", "multiplier"), DOCUMENTED_TABLE)
def test_documented_table(all_time: float, chips: int, multiplier: float) -> None:
    assert chips_for(all_time) == chips
    assert multiplier_for(chips) == pytest.approx(multiplier)


def test_below_the_divisor_earns_nothing() -> None:
    assert chips_for(0.0) == 0
    assert chips_for(-1.0) == 0
    assert chips_for(CHIP_DIVISOR - 1.0) == 0
    assert multiplier_for(0) == 1.0


def test_exact_cubes_are_not_lost_to_the_cube_root() -> None:
    """A naive int((a / 1e9) ** (1 / 3)) pays 9 chips at 1e12. The forward check pays 10."""
    assert (1e12 / CHIP_DIVISOR) ** (1.0 / 3.0) == 9.999999999999998
    for chips in (1, 2, 3, 10, 21, 46, 100, 1_000, 10_000, 100_000):
        exact = cookies_for_chips(chips)
        assert chips_for(exact) == chips, f"{chips} chips at exactly {exact}"


def test_one_cookie_short_of_a_cube_pays_the_lower_count() -> None:
    for chips in (2, 10, 100, 1_000):
        just_under = cookies_for_chips(chips) * (1.0 - 1e-12)
        assert chips_for(just_under) == chips - 1


def test_chips_never_decrease_as_lifetime_grows() -> None:
    previous = 0
    total = CHIP_DIVISOR
    while total < 1e30:
        current = chips_for(total)
        assert current >= previous
        previous = current
        total *= 1.6
    assert previous > 1_000


def test_cookies_for_chips_is_the_inverse_of_chips_for() -> None:
    for chips in range(1, 200):
        required = cookies_for_chips(chips)
        assert chips_for(required) == chips
        assert chips_for(required * 0.999) == chips - 1


def test_multiplier_is_linear_in_chips() -> None:
    assert multiplier_for(1) - multiplier_for(0) == pytest.approx(CHIP_MULTIPLIER)
    assert multiplier_for(41) - multiplier_for(40) == pytest.approx(CHIP_MULTIPLIER)
    assert multiplier_for(20) == pytest.approx(2.0)
