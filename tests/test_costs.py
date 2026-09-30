"""Cost identities and exactness, per docs/ARCHITECTURE.md §5.3 and docs/BALANCE.md §2."""

from __future__ import annotations

import math

import pytest

from cookie.engine.costs import GROWTH, MAX_BULK, bulk_cost, max_affordable, unit_cost

BASES = [15.0, 100.0, 1_100.0, 130_000.0, 1.4e13]


def _naive_bulk_cost(base: float, owned: int, count: int) -> float:
    """Sum of the exact unit prices, without the single ceiling. Reference for the closed form."""
    return sum(base * GROWTH ** (owned + i) for i in range(count))


def _naive_max_affordable(base: float, owned: int, cookies: float) -> int:
    count = 0
    while count < MAX_BULK and bulk_cost(base, owned, count + 1) <= cookies:
        count += 1
    return count


def test_documented_examples() -> None:
    assert unit_cost(15.0, 0) == 15
    assert unit_cost(15.0, 10) == 61
    assert bulk_cost(15.0, 0, 10) == 305
    assert bulk_cost(15.0, 0, 100) == 117_431_246
    assert max_affordable(15.0, 0, 1_000.0) == 17
    assert bulk_cost(15.0, 0, 17) == 977
    assert bulk_cost(15.0, 0, 18) == 1_138


@pytest.mark.parametrize("base", BASES)
def test_unit_cost_equals_bulk_cost_of_one(base: float) -> None:
    for owned in range(501):
        assert unit_cost(base, owned) == bulk_cost(base, owned, 1)


def test_bulk_cost_of_nothing_is_free() -> None:
    assert bulk_cost(15.0, 0, 0) == 0.0
    assert bulk_cost(15.0, 7, -3) == 0.0


@pytest.mark.parametrize("base", BASES)
def test_bulk_cost_is_strictly_increasing_in_count(base: float) -> None:
    previous = 0.0
    for count in range(1, 60):
        cost = bulk_cost(base, 3, count)
        assert cost > previous
        previous = cost


def test_bulk_cost_tracks_the_exact_geometric_sum_while_integers_are_exact() -> None:
    """Below 2**53 the single ceiling adds less than one cookie to the exact sum, never more."""
    checked = 0
    for owned in range(0, 200, 7):
        for count in (1, 2, 5, 13, 50):
            exact = _naive_bulk_cost(15.0, owned, count)
            if exact >= 2.0**53:
                continue
            charged = bulk_cost(15.0, owned, count)
            assert exact <= charged < exact + 1.0 + 1e-6
            checked += 1
    assert checked > 50, "the sweep stopped covering the exact-integer range"


def test_bulk_cost_stays_within_double_precision_above_the_integer_range() -> None:
    """Past 2**53 a cookie is below one ULP, so the guarantee is relative, not absolute."""
    for owned in (200, 300, 400, 500):
        for count in (2, 7, 40):
            exact = _naive_bulk_cost(15.0, owned, count)
            charged = bulk_cost(15.0, owned, count)
            assert charged == pytest.approx(exact, rel=1e-12)


@pytest.mark.parametrize("base", [15.0, 1_100.0, 130_000.0])
def test_max_affordable_matches_a_brute_force_loop(base: float) -> None:
    cookie_sweep = [0.0, 1.0, base - 1, base, base * 1.5]
    cookie_sweep += [base * 10.0**exponent for exponent in range(9)]
    for owned in range(0, 61, 5):
        for cookies in cookie_sweep:
            assert max_affordable(base, owned, cookies) == _naive_max_affordable(
                base, owned, cookies
            ), f"base={base} owned={owned} cookies={cookies}"


def test_max_affordable_answer_is_actually_affordable() -> None:
    """Whatever "buy max" reports must be payable, and one more must not be."""
    for owned in (0, 1, 17, 99):
        for cookies in (0.0, 14.0, 15.0, 305.0, 1e6, 1e12):
            count = max_affordable(15.0, owned, cookies)
            assert bulk_cost(15.0, owned, count) <= cookies
            if count < MAX_BULK:
                assert bulk_cost(15.0, owned, count + 1) > cookies


def test_max_affordable_is_zero_below_the_unit_price() -> None:
    assert max_affordable(15.0, 0, 0.0) == 0
    assert max_affordable(15.0, 0, 14.99) == 0
    assert max_affordable(15.0, 0, 15.0) == 1


def test_max_affordable_never_exceeds_the_bulk_cap() -> None:
    """With real base costs the price overflows well before MAX_BULK, which is the guard's job."""
    count = max_affordable(15.0, 0, 1e300)
    assert count <= MAX_BULK
    assert count > 4_000, "a fortune should still buy thousands of the cheapest building"
    assert math.isinf(bulk_cost(15.0, 0, count + 1)) or bulk_cost(15.0, 0, count + 1) > 1e300


def test_huge_owned_counts_return_infinity_instead_of_raising() -> None:
    """`float ** int` raises OverflowError; an unreachable count must not take the game down."""
    assert unit_cost(15.0, 100_000) == math.inf
    assert bulk_cost(15.0, 100_000, 1) == math.inf
    assert bulk_cost(15.0, 100_000, 5) == math.inf
    assert max_affordable(15.0, 100_000, 1e308) == 0


def test_growth_is_fifteen_percent() -> None:
    assert GROWTH == 1.15
    assert unit_cost(100.0, 1) == 115
