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
"""The variants of the method, behind the interface of the baselines.

Each variant changes **one thing** from the swept configuration, the one a user
gets having tuned nothing, so that its profile measures that one thing:

- the **probes** of the master, which are also the rungs of the convexity
  ladder, so that more of them explore more boxes per iteration *and* try more
  convexity values;
- the **top of the ladder**, a low one keeping the master near the boxes the cuts
  favour and a high one sending it across the design space;
- the **density**, fixed at ten per variable or proposed per component by the
  basin count of :mod:`benchmarks.basin_spacing`, whose scans are paid out of the
  same budget;
- the **multi-resolution encoding** and the **deep hierarchy**, the two
  extensions reaching a resolution the flat subdivision cannot afford in
  binaries.

The calibrated configuration is here too, as the reference the sweep replaced.
Every runner returns a :class:`.Result` carrying its history, which is what
:mod:`benchmarks.data_profiles` compares.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING

from numpy import array

from benchmarks import baselines
from benchmarks.baselines import BudgetedCounter
from benchmarks.baselines import Result
from benchmarks.baselines import run_box_subdivision
from benchmarks.baselines import run_swept_box_subdivision
from benchmarks.problems import Counter
from gemseo_box_subdivision import SweptBoxSubdivisionSettings

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Iterator

    from benchmarks.problems import Problem


@contextmanager
def _capturing_counters() -> Iterator[list[BudgetedCounter]]:
    """Collect the budgeted counters created while the context is open.

    The runners of the extensions report only a best value and a cost, and keep
    the counter holding the history to themselves.

    Yields:
        The counters, in the order they were created.
    """
    counters = []
    original = BudgetedCounter.__init__

    def init(self, *args, **kwargs) -> None:  # noqa: ANN001, ANN002, ANN003
        original(self, *args, **kwargs)
        counters.append(self)

    BudgetedCounter.__init__ = init
    try:
        yield counters
    finally:
        BudgetedCounter.__init__ = original


def _result(
    name: str, problem: Problem, dimension: int, seed: int, counter: Counter
) -> Result:
    """Assemble the outcome of a run from its counter.

    Args:
        name: The name of the variant.
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the run.
        counter: The counter of the calls.

    Returns:
        The outcome of the run.
    """
    return baselines._result(name, problem, dimension, seed, counter, adjoint=True)


def run_swept(
    name: str,
    problem: Problem,
    dimension: int,
    seed: int,
    budget: int,
    **settings: float,
) -> Result:
    """Run the swept configuration with some of its settings changed.

    Args:
        name: The name of the variant.
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the starting point.
        budget: The budget in equivalent evaluations.
        **settings: The settings of :func:`.run_swept_box_subdivision` to change.

    Returns:
        The outcome of the run.
    """
    result = run_swept_box_subdivision(
        problem, dimension, seed, budget, True, **settings
    )
    return replace(result, method=name)


def run_calibrated(problem: Problem, dimension: int, seed: int, budget: int) -> Result:
    """Run the calibrated configuration, the convexity margin set to 100.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the starting point.
        budget: The budget in equivalent evaluations.

    Returns:
        The outcome of the run.
    """
    result = run_box_subdivision(problem, dimension, seed, budget, True)
    return replace(result, method="margin_100")


def run_proposed_density(
    problem: Problem,
    dimension: int,
    seed: int,
    budget: int,
    charge_scans: bool = True,
) -> Result:
    """Propose a density per component by counting basins, then run it swept.

    The scans evaluate the objective, so they are paid out of the budget and
    come first in the history: the profile of this variant starts with the
    evaluations spent deciding the density, and whatever the scans find counts.
    They cost more than the runs they configure, several thousand evaluations
    on most problems, so the variant is also run with the scans **free**, which
    is what the density proposed is worth rather than what proposing it costs.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the scans and of the starting point.
        budget: The budget in equivalent evaluations.
        charge_scans: Whether the scans are paid out of the budget.

    Returns:
        The outcome of the run.
    """
    from benchmarks.basin_spacing import estimate_basins
    from benchmarks.basin_spacing import run_at_density_swept

    scans = Counter(problem)
    estimate = estimate_basins(
        lambda points: array([scans.objective(point) for point in points]),
        problem.lower_bound,
        problem.upper_bound,
        dimension=dimension,
        seed=seed,
    )
    history = list(scans.history(dimension, adjoint=True)) if charge_scans else []
    remaining = budget - len(history)
    counter = None
    if remaining > 0:
        with _capturing_counters() as counters:
            run_at_density_swept(
                problem, dimension, estimate.n_subdivisions, seed, remaining
            )

        counter = counters[0]
        found = scans.best if charge_scans else float("inf")
        history += [min(found, best) for best in counter.history(dimension, True)]

    history = history[:budget]
    n_gradient = counter.n_gradient if counter else 0
    return Result(
        method="proposed_density" if charge_scans else "proposed_density_free",
        problem=problem.name,
        dimension=dimension,
        seed=seed,
        best=min(history),
        n_objective=scans.n_objective * charge_scans
        + (counter.n_objective if counter else 0),
        n_gradient=n_gradient,
        cost_adjoint=len(history),
        cost_finite_differences=len(history) + (dimension - 1) * n_gradient,
        budget=budget,
        history=tuple(history),
    )


def run_deep_hierarchy(
    problem: Problem, dimension: int, seed: int, budget: int
) -> Result:
    """Refine the best box four times, splitting every variable in two.

    Every level is run swept and they share one budget, so the resolution
    reached is sixteen per variable at the binaries of two.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the starting point.
        budget: The budget in equivalent evaluations.

    Returns:
        The outcome of the run.
    """
    from benchmarks.configurations import TRUST_REGION_RADIUS
    from benchmarks.hierarchy import run_deep

    with _capturing_counters() as counters:
        run_deep(
            problem,
            dimension,
            seed,
            budget,
            box_settings=SweptBoxSubdivisionSettings(
                trust_region_radius=TRUST_REGION_RADIUS, max_iter=10000
            ),
        )

    return _result("deep_hierarchy", problem, dimension, seed, counters[0])


VARIANTS: dict[str, tuple[str, Callable[[Problem, int, int, int], Result]]] = {
    "swept": ("swept, 4 probes", partial(run_swept, "swept")),
    "margin_100": ("calibrated, margin 100", run_calibrated),
    "probes_8": (
        "swept, 8 probes",
        partial(run_swept, "probes_8", n_parallel_points=8),
    ),
    "probes_16": (
        "swept, 16 probes",
        partial(run_swept, "probes_16", n_parallel_points=16),
    ),
    "ceiling_30": (
        "swept, ladder up to 30",
        partial(run_swept, "ceiling_30", max_value=30.0),
    ),
    "ceiling_10": (
        "swept, ladder up to 10",
        partial(run_swept, "ceiling_10", max_value=10.0),
    ),
    "density_10": (
        "swept, 10 per variable",
        partial(run_swept, "density_10", n_subdivisions=10),
    ),
    "proposed_density": ("swept, proposed density", run_proposed_density),
    "proposed_density_free": (
        "swept, proposed density, scans free",
        partial(run_proposed_density, charge_scans=False),
    ),
    "density_10_ceiling_10": (
        "swept, 10 per variable, ladder up to 10",
        partial(run_swept, "density_10_ceiling_10", n_subdivisions=10, max_value=10.0),
    ),
    "multi_resolution": (
        "swept, 2 levels of 4",
        partial(run_swept, "multi_resolution", n_subdivisions=4, levels=2),
    ),
    "deep_hierarchy": ("swept, deep hierarchy", run_deep_hierarchy),
}
"""The label and the runner of each variant, by name."""


def run(
    variant: str, problem: Problem, dimension: int, seed: int, budget: int
) -> Result:
    """Run one variant on one problem.

    Args:
        variant: The name of the variant.
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the run.
        budget: The budget in equivalent evaluations.

    Returns:
        The outcome of the run.
    """
    logging.disable(logging.CRITICAL)
    try:
        return VARIANTS[variant][1](problem, dimension, seed, budget)
    finally:
        logging.disable(logging.NOTSET)
