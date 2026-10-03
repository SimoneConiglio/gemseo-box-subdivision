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

The full study is :mod:`benchmarks.data_profiles`, which takes hours for EGO;
these run the fast methods on two problems, which is enough to check that a
history counts what the budget counts, that a profile is a fraction of the
targets, and that a variant charges what it spends.
"""

from __future__ import annotations

import json

import pytest
from numpy import diff
from numpy import ones

from benchmarks.baselines import run
from benchmarks.data_profiles import budget_of
from benchmarks.data_profiles import change_points
from benchmarks.data_profiles import collect
from benchmarks.data_profiles import compute_profiles
from benchmarks.data_profiles import compute_targets
from benchmarks.data_profiles import targeting_the_optimum
from benchmarks.problems import PROBLEMS
from benchmarks.problems import Counter
from benchmarks.variants import run as run_variant

METHODS = ("swept", "ceiling_10", "cmaes", "direct")
"""The methods of this check, variants and baselines running in seconds."""

PROBLEM_NAMES = ("rastrigin", "styblinski_tang")
"""The problems of this check."""


@pytest.fixture(scope="module")
def results():
    """Run the methods on the problems in two dimensions, from two points."""
    return collect(2, METHODS, PROBLEM_NAMES, (11, 101), max_workers=2)


def test_cache(tmp_path) -> None:
    """Check that a finished run is read back rather than run again."""
    cache = tmp_path / "2.jsonl"
    first = collect(2, ("direct",), ("rastrigin",), (11,), 1, cache)
    # Tampered with, so that a run read back is told from a run repeated.
    data = json.loads(cache.read_text(encoding="utf-8"))
    cache.write_text(json.dumps({**data, "best": 7.0}) + "\n", encoding="utf-8")
    second = collect(2, ("direct",), ("rastrigin",), (11,), 1, cache)
    assert second[0].history == first[0].history
    assert second[0].best == pytest.approx(7.0)


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
    for method, profile in profiles.items():
        assert len(profile) == budget_of(method, 2)
        assert 0.0 <= profile[0] <= profile[-1] <= 1.0
        assert all(step >= 0.0 for step in diff(profile))


@pytest.mark.parametrize(
    ("variant", "charged"),
    [("proposed_density", True), ("proposed_density_free", False)],
)
def test_proposed_density_charges_its_scans(variant, charged) -> None:
    """Check that the scans count against the budget only when charged.

    The scans of Rastrigin cost more than a budget of a thousand, so a charged
    run is all scans and a free one is all method.
    """
    result = run_variant(variant, PROBLEMS["rastrigin"], 2, 11, 1000)
    assert len(result.history) == result.cost_adjoint <= 1000
    assert (result.n_gradient == 0) is charged


def test_change_points() -> None:
    """Check that a profile is redrawn from where it changes."""
    assert change_points([0.0, 0.0, 0.5, 0.5, 1.0, 1.0]) == [
        (1, 0.0),
        (3, 0.5),
        (5, 1.0),
        (6, 1.0),
    ]
