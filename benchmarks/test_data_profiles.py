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
"""Check the histories the data profiles read, and the profiles themselves.

The full study is :mod:`benchmarks.data_profiles`, which takes an hour for EGO;
these run the fast methods on two problems, which is enough to check that a
history counts what the budget counts and that a profile is a fraction of the
targets.
"""

from __future__ import annotations

import pytest
from numpy import diff
from numpy import ones

from benchmarks.baselines import run
from benchmarks.data_profiles import BUDGET
from benchmarks.data_profiles import collect
from benchmarks.data_profiles import compute_profiles
from benchmarks.data_profiles import compute_targets
from benchmarks.data_profiles import targeting_the_optimum
from benchmarks.problems import PROBLEMS
from benchmarks.problems import Counter

METHODS = ("box_subdivision_swept", "cmaes", "direct")
"""The methods of this check, those running in seconds."""

PROBLEM_NAMES = ("rastrigin", "styblinski_tang")
"""The problems of this check."""


@pytest.fixture(scope="module")
def results():
    """Run the methods on the problems in two dimensions, from two points."""
    return collect(2, METHODS, PROBLEM_NAMES, (11, 101), max_workers=2)


@pytest.mark.parametrize("method", ["box_subdivision", "multistart", "cmaes"])
def test_history_counts_the_cost(method) -> None:
    """Check that a history has one entry per equivalent evaluation.

    A data profile reads the entry at index ``i`` as the best value after
    ``i + 1`` evaluations, so a gradient has to span what it costs.
    """
    result = run(method, PROBLEMS["rastrigin"], 2, 11, 200)
    assert len(result.history) == result.cost_adjoint
    assert list(result.history) == sorted(result.history, reverse=True)
    assert result.history[-1] == result.best


def test_history_under_finite_differences() -> None:
    """Check that a gradient spans as many entries as there are variables."""
    counter = Counter(PROBLEMS["rastrigin"])
    counter.objective(ones(3))
    counter.gradient(ones(3))
    assert len(counter.history(3, adjoint=True)) == 2
    assert len(counter.history(3, adjoint=False)) == 4
    assert counter.history(3, adjoint=False) == (counter.best,) * 4


def test_targets(results) -> None:
    """Check that the targets descend to the optimum where a run reached it."""
    targets = compute_targets(results)
    assert set(targets) == set(PROBLEM_NAMES)
    for values in targets.values():
        assert all(step <= 0.0 for step in diff(values))

    # DIRECT solves both problems in two dimensions within the budget.
    assert targeting_the_optimum(targets, 2) == list(targets)


def test_profiles(results) -> None:
    """Check that a profile is a non-decreasing fraction, over the budget."""
    profiles = compute_profiles(results, compute_targets(results))
    assert set(profiles) == set(METHODS)
    for profile in profiles.values():
        assert len(profile) == BUDGET
        assert 0.0 <= profile[0] <= profile[-1] <= 1.0
        assert all(step >= 0.0 for step in diff(profile))
