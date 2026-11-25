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
"""Compare the box-subdivision outer approximation with the usual baselines.

The baselines are the methods that actually address this problem class, a
multimodal non-linear program driven by a local solver:

- **multistart** of a local solver, the reference of the class;
- **CMA-ES**, an evolution strategy, which does not use the gradient;
- **DIRECT**, a deterministic partitioning method, which does not either;
- **tunneling**, a deterministic sequence of local solutions, each started
  from a point below the level of the last minimum.

Relaxation-based global solvers such as BARON or Alpine are deliberately absent:
they require an algebraic form of the problem to build their relaxations, which
the sub-problem of an industrial case does not have.

Every method is stopped at the same budget of equivalent objective evaluations,
under both gradient-cost conventions, see :mod:`benchmarks.baselines`.
"""

from __future__ import annotations

import logging

import pytest
from numpy import isfinite
from numpy import median

from benchmarks.baselines import METHODS
from benchmarks.baselines import run
from benchmarks.problems import PROBLEMS

BUDGET = 1000
"""The budget in equivalent objective evaluations."""

DIMENSION = 2
"""The number of design variables."""

SEEDS = (11, 101)
"""The seeds of the starting points."""

COMPARED_PROBLEMS = ("rastrigin", "styblinski_tang")
"""The problems of this comparison, kept short enough to run in the tests."""


@pytest.fixture(scope="module")
def results():
    """Run every method on every problem, from every starting point."""
    logging.disable(logging.CRITICAL)
    records = [
        run(method, PROBLEMS[name], DIMENSION, seed, BUDGET)
        for name in COMPARED_PROBLEMS
        for seed in SEEDS
        for method in METHODS
    ]
    logging.disable(logging.NOTSET)
    return records


def test_report(results) -> None:
    """Print the comparison at equal budget."""
    print(
        f"\nbudget {BUDGET} equivalent evaluations, {DIMENSION} design variables\n"
        f"{'problem':>16} {'method':>16} {'gap':>10} {'n_obj':>7} {'n_grad':>7}"
        f" {'adjoint':>8} {'fd':>7}"
    )
    for record in results:
        optimum = PROBLEMS[record.problem].optimum(record.dimension)
        print(
            f"{record.problem:>16} {record.method:>16} "
            f"{record.gap(optimum):>10.4f} {record.n_objective:>7d} "
            f"{record.n_gradient:>7d} {record.cost_adjoint:>8d} "
            f"{record.cost_finite_differences:>7d}"
        )


@pytest.mark.parametrize("method", METHODS)
def test_every_method_actually_runs(results, method) -> None:
    """Check that no method silently does nothing.

    A method whose settings are rejected would otherwise return an infinite
    objective after no evaluation at all, and appear to lose fairly.
    """
    records = [record for record in results if record.method == method]
    assert records
    for record in records:
        assert record.n_objective > 0, f"{method} evaluated nothing"
        assert isfinite(record.best), f"{method} returned no finite value"


BUDGET_TOLERANCE = 1.05
"""The overshoot allowed on the budget.

DIRECT evaluates its objective by batches of sample points and finishes the
batch that reaches the limit, so it overshoots its own ``maxfun`` slightly.
"""


@pytest.mark.parametrize("method", METHODS)
def test_no_method_exceeds_its_budget(results, method) -> None:
    """Check that the budget is enforced, so the comparison is at equal cost."""
    for record in results:
        if record.method == method:
            assert record.cost_adjoint <= BUDGET * BUDGET_TOLERANCE


def _median_gaps(results, problem: str) -> dict[str, float]:
    """Return the median distance to the optimum of each method on a problem.

    Args:
        results: The outcome of the runs.
        problem: The name of the problem.

    Returns:
        The median distance to the optimum of each method.
    """
    optimum = PROBLEMS[problem].optimum(DIMENSION)
    return {
        method: float(
            median([
                record.gap(optimum)
                for record in results
                if record.method == method and record.problem == problem
            ])
        )
        for method in METHODS
    }


def test_summary(results) -> None:
    """Print the median distance to the optimum, per problem and method."""
    print(f"\nmedian gap to the optimum over {len(SEEDS)} starting points")
    print(f"{'problem':>16} " + " ".join(f"{method:>16}" for method in METHODS))
    for problem in COMPARED_PROBLEMS:
        gaps = _median_gaps(results, problem)
        print(f"{problem:>16} " + " ".join(f"{gaps[m]:>16.4f}" for m in METHODS))


def test_matches_the_reference_where_the_convexification_is_tuned(results) -> None:
    """Check the method against multistart on the problem it was tuned on.

    The convexification constant of the method was tuned on Rastrigin, and only
    there is the comparison with multistart, the reference of this problem
    class, a statement about the method rather than about the tuning.
    """
    gaps = _median_gaps(results, "rastrigin")
    assert gaps["box_subdivision"] <= gaps["multistart"] + 1e-6
