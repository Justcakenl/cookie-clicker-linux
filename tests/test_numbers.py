"""Formatter totality and exact output, per docs/ARCHITECTURE.md §11."""

from __future__ import annotations

import math
import sys
from collections.abc import Callable

import pytest

from cookie.engine.numbers import (
    SCALES,
    SCIENTIFIC_THRESHOLD,
    format_duration,
    format_rate,
    format_raw,
    format_scientific,
    format_short,
    formatter_for,
)

# Widths the UI's fixed columns are sized for. format_short sets the cookie and CPS columns; the
# other two are opt-in settings and only need to be bounded, not narrow.
MAX_WIDTH = {"format_short": 17, "format_scientific": 11, "format_raw": 28}

EXACT_CASES = [
    (0.0, "0"),
    (-0.0, "0"),
    (0.5, "0.5"),
    (1.0, "1"),
    (1.5, "1.5"),
    (12.25, "12.25"),
    (99.999, "100"),
    (100.0, "100"),
    (999.0, "999"),
    (1_000.0, "1.00 thousand"),
    (1_234.0, "1.23 thousand"),
    (12_345.0, "12.3 thousand"),
    (123_456.0, "123 thousand"),
    (999_999.0, "1000 thousand"),
    (1_000_000.0, "1.00 million"),
    (1.23e6, "1.23 million"),
    (4.56e9, "4.56 billion"),
    (1e12, "1.00 trillion"),
    (1e15, "1.00 quadrillion"),
    (1e18, "1.00 quintillion"),
    (1e21, "1.00 sextillion"),
    (1e24, "1.00 septillion"),
    (1e27, "1.00 octillion"),
    (1e30, "1.00 nonillion"),
    (1e33, "1.00 decillion"),
    (9.99e35, "999 decillion"),
    (1e36, "1.000e+36"),
    (1e308, "1.000e+308"),
    (-1_234.0, "-1.23 thousand"),
]


@pytest.mark.parametrize(("value", "expected"), EXACT_CASES)
def test_format_short_exact(value: float, expected: str) -> None:
    assert format_short(value) == expected


def test_format_short_scale_names_are_reachable() -> None:
    """Every scale in the table is actually used by some value below the scientific threshold."""
    for exponent, name in SCALES:
        assert name in format_short(10.0**exponent)


def test_scientific_switch_is_exactly_at_the_threshold() -> None:
    assert "e+" not in format_short(math.nextafter(SCIENTIFIC_THRESHOLD, 0.0))
    assert "e+" in format_short(SCIENTIFIC_THRESHOLD)


def _hostile_values() -> list[float]:
    values: list[float] = [
        0.0,
        -0.0,
        1e-9,
        -1e-9,
        math.inf,
        -math.inf,
        math.nan,
        sys.float_info.max,
        -sys.float_info.max,
        sys.float_info.min,
    ]
    for exponent in range(309):
        power = 10.0**exponent
        values.extend([power, -power, math.nextafter(power, 0.0), power * 0.999])
    return values


@pytest.mark.parametrize("formatter", [format_short, format_scientific, format_raw])
def test_formatters_never_raise_and_stay_bounded(formatter: Callable[[float], str]) -> None:
    limit = MAX_WIDTH[formatter.__name__]
    for value in _hostile_values():
        rendered = formatter(value)
        assert rendered
        assert len(rendered) <= limit, f"{value!r} rendered {len(rendered)} chars: {rendered}"


def test_format_short_fits_the_cookie_column_for_every_reachable_value() -> None:
    """Cookie counts are never negative, so the column only has to fit the positive width."""
    for value in (v for v in _hostile_values() if not math.isnan(v) and v >= 0.0):
        assert len(format_short(value)) <= 16


def test_format_short_is_monotone_in_magnitude() -> None:
    """Rendered magnitude never decreases as the value grows, so the counter cannot go back."""
    previous = -math.inf
    value = 1.0
    while value < SCIENTIFIC_THRESHOLD:
        rendered = format_short(value)
        magnitude = _parse_magnitude(rendered)
        assert magnitude >= previous * 0.999, f"{rendered} went backwards from {previous}"
        previous = magnitude
        value *= 1.7
    assert previous > 0.0


_SCALE_BY_NAME = {name: exponent for exponent, name in SCALES}


def _parse_magnitude(rendered: str) -> float:
    if " " in rendered:
        mantissa, name = rendered.split(" ", 1)
        return float(mantissa) * 10.0 ** _SCALE_BY_NAME[name]
    return float(rendered.replace(",", ""))


def test_non_finite_renders_as_words() -> None:
    assert format_short(math.nan) == "?"
    assert format_short(math.inf) == "inf"
    assert format_short(-math.inf) == "-inf"
    assert format_raw(math.nan) == "?"
    assert format_scientific(math.inf) == "inf"


def test_format_rate_keeps_a_decimal_below_a_thousand() -> None:
    assert format_rate(0.0) == "0.0/s"
    assert format_rate(0.1) == "0.1/s"
    assert format_rate(12.44) == "12.4/s"
    assert format_rate(999.9) == "999.9/s"
    assert format_rate(1000.0) == "1.00 thousand/s"
    assert format_rate(4.56e9) == "4.56 billion/s"
    assert format_rate(math.nan) == "?/s"


def test_format_duration_uses_the_largest_two_units() -> None:
    assert format_duration(0.0) == "0s"
    assert format_duration(-5.0) == "0s"
    assert format_duration(1.0) == "1s"
    assert format_duration(59.9) == "59s"
    assert format_duration(60.0) == "1m"
    assert format_duration(61.0) == "1m 1s"
    assert format_duration(3_600.0) == "1h"
    assert format_duration(3_661.0) == "1h 1m"
    assert format_duration(90_000.0) == "1d 1h"
    assert format_duration(86_400.0 * 3 + 3_600.0 * 4 + 720.0) == "3d 4h"
    assert format_duration(math.inf) == "forever"
    assert format_duration(math.nan) == "0s"


def test_formatter_for_selects_by_setting() -> None:
    assert formatter_for("short") is format_short
    assert formatter_for("scientific") is format_scientific
    assert formatter_for("raw") is format_raw


def test_scientific_and_raw_render_the_same_value_differently() -> None:
    assert format_scientific(1_234_567.0) == "1.235e+06"
    assert format_raw(1_234_567.0) == "1,234,567"
    assert format_scientific(12.5) == "12.5"
