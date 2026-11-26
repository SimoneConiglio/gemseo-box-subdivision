# Copyright 2026 Simone Coniglio
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""Tests for the paired statistics of the comparison with the baselines."""

from __future__ import annotations

import pytest

from benchmarks.statistics import change_points
from benchmarks.statistics import clearly_better
from benchmarks.statistics import holm
from benchmarks.statistics import mcnemar
from benchmarks.statistics import run_area
from benchmarks.statistics import signed_rank


def test_holm_multiplies_by_the_rank_and_stays_monotone() -> None:
    """The Holm procedure must scale the sorted p-values and keep their order."""
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])


def test_mcnemar_counts_only_the_discordant_starts() -> None:
    """Seven discordant starts in one direction give the exact binomial p-value."""
    first = [True] * 7 + [True, False]
    second = [False] * 7 + [True, False]
    assert mcnemar(first, second) == (7, 0, pytest.approx(2 * 0.5**7))
    assert mcnemar([True, False], [True, False]) == (0, 0, 1.0)


def test_identical_distances_are_not_a_difference() -> None:
    """Equal distances on every start must give a p-value of one."""
    assert signed_rank([0.0, 1.0], [0.0, 1.0]) == pytest.approx(1.0)


def test_the_area_of_a_run_is_the_mean_fraction_of_targets() -> None:
    """A run reaching one target of two at the second of four evaluations."""
    assert run_area([3.0, 1.0], [2.0, 0.0], 4) == pytest.approx(3 / 8)


def test_the_history_keeps_only_the_improvements() -> None:
    """The change points must hold the first value and every improvement."""
    assert change_points([3.0, 3.0, 2.0, 2.0, 1.0]) == [[1, 3.0], [3, 2.0], [5, 1.0]]


def _test(only_method: int, only_challenger: int, p_holm: float) -> dict:
    """Return a test of the configuration against a challenger."""
    return {
        "only_method": only_method,
        "only_baseline": only_challenger,
        "p_success_holm": p_holm,
    }


@pytest.mark.parametrize(
    ("tests", "upper", "expected"),
    [
        ([_test(0, 11, 0.01), _test(0, 0, 1.0)], 0.01, True),
        ([_test(0, 11, 0.01), _test(9, 0, 0.04)], -0.01, False),
        ([_test(0, 3, 0.9)], -0.01, True),
        ([_test(0, 3, 0.9)], 0.01, False),
    ],
)
def test_a_challenger_is_clearly_better_only_without_a_significant_loss(
    tests: list[dict], upper: float, expected: bool
) -> None:
    """A significant gain or a larger area, and no significant loss."""
    assert clearly_better(tests, {"ci95": [upper - 0.1, upper]}) is expected
