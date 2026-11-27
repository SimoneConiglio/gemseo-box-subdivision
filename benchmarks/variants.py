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


@contextmanager
def _master_replaced(mode: str, seed: int) -> Iterator[None]:
    """Replace a part of the master problem, for an ablation.

    Args:
        mode: ``"random_box"`` to select a box at random among the boxes not yet
            solved within the trust region of the probe, instead of solving the
            mixed-integer program; ``"zero_slopes"`` to set the slopes of the
            cuts to zero before the repair, so that the cuts carry only the
            values observed; ``"random_slopes"`` to replace each slope by a
            random vector of the same norm before the repair.
        seed: The seed of the random selection.

    Yields:
        Nothing.
    """
    from gemseo_bilevel_outer_approximation.algos.opt.core import (  # noqa: PLC0415
        outer_approximation_optimizer as core,
    )
    from numpy import argmax  # noqa: PLC0415
    from numpy import inf  # noqa: PLC0415
    from numpy import zeros_like  # noqa: PLC0415
    from numpy.random import default_rng  # noqa: PLC0415

    original = core.OuterApproximationOptimizer._solve_milp
    rng = default_rng(seed)

    def blocks(self) -> list[int]:
        """Return the size of each one-hot group, in the order of alpha."""
        return [
            self.n_catalogues[name]
            for name in self.design_space.variable_names
            if not self.design_space.hypercube[name]
            for _ in range(self.n_members[name])
        ]

    def random_box(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        excluded = {tuple(a) for group in (args[1], args[9], args[11]) for a in group}
        incumbent = array(args[13], dtype=float)
        radius = int(kwargs.get("current_step", args[-1]) + 1e-9)
        sizes = blocks(self)
        starts = [sum(sizes[:k]) for k in range(len(sizes))]
        current = [
            int(argmax(incumbent[b : b + m]))
            for b, m in zip(starts, sizes, strict=True)
        ]
        for _ in range(10_000):
            changed = rng.choice(
                len(sizes), size=int(rng.integers(1, radius + 1)), replace=False
            )
            alpha = zeros_like(incumbent)
            for k, (b, m) in enumerate(zip(starts, sizes, strict=True)):
                index = current[k]
                if k in changed and m > 1:
                    index = int(rng.choice([i for i in range(m) if i != current[k]]))
                alpha[b + index] = 1.0
            if tuple(alpha) not in excluded:
                return alpha, -inf, True
        return incumbent, -inf, True

    def random_slopes(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        args = list(args)
        for k in (0, 10):
            args[k] = [
                rng.standard_normal(array(s).size).reshape(array(s).shape)
                * float((array(s, dtype=float) ** 2).sum() ** 0.5)
                / max(array(s).size, 1) ** 0.5
                for s in args[k]
            ]
        return original(self, *args, **kwargs)

    def zero_slopes(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        args = list(args)
        args[0] = [zeros_like(array(s, dtype=float)) for s in args[0]]
        args[10] = [zeros_like(array(s, dtype=float)) for s in args[10]]
        return original(self, *args, **kwargs)

    core.OuterApproximationOptimizer._solve_milp = {
        "random_box": random_box,
        "zero_slopes": zero_slopes,
        "random_slopes": random_slopes,
    }[mode]
    try:
        yield
    finally:
        core.OuterApproximationOptimizer._solve_milp = original


def run_ablation(
    mode: str, problem: Problem, dimension: int, seed: int, budget: int
) -> Result:
    """Run the configuration with a part of its master problem replaced.

    Args:
        mode: The part replaced, see :func:`._master_replaced`.
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the starting point and of the random selection.
        budget: The budget in equivalent evaluations.

    Returns:
        The outcome of the run.
    """
    n_subdivisions = 10 if dimension == 5 else 0
    with _master_replaced(mode, seed):
        result = run_swept_box_subdivision(
            problem, dimension, seed, budget, True, n_subdivisions=n_subdivisions
        )
    return replace(result, method=mode)


def run_calibrated(
    problem: Problem,
    dimension: int,
    seed: int,
    budget: int,
    n_subdivisions: int = 0,
    name: str = "margin_100",
) -> Result:
    """Run the calibrated configuration, the convexity margin set to 100.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the starting point.
        budget: The budget in equivalent evaluations.
        n_subdivisions: The number of subdivisions per variable.
            If zero, use :func:`.default_n_subdivisions`.
        name: The name of the variant.

    Returns:
        The outcome of the run.
    """
    result = run_box_subdivision(
        problem, dimension, seed, budget, True, n_subdivisions=n_subdivisions
    )
    return replace(result, method=name)


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


EUCLIDEAN_DIAMETER = {
    "trust_region_metric": "euclidean",
    "trust_region_schedule": "diameter",
}
"""The Euclidean trust region starting at the diameter of the subdivision."""

EUCLIDEAN_NEAREST = {
    "trust_region_metric": "euclidean",
    "trust_region_anchor": "nearest",
    "trust_region_radius": 1.5,
}
"""The union of the balls of radius 1.5 around the evaluated boxes."""

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
    "euclidean_diameter": (
        "swept, Euclidean, diameter",
        partial(
            run_swept,
            "euclidean_diameter",
            trust_region=EUCLIDEAN_DIAMETER,
        ),
    ),
    "euclidean_nearest": (
        "swept, Euclidean, nearest box",
        partial(run_swept, "euclidean_nearest", trust_region=EUCLIDEAN_NEAREST),
    ),
    "density_10_margin_100": (
        "calibrated, margin 100, 10 per variable",
        partial(run_calibrated, n_subdivisions=10, name="density_10_margin_100"),
    ),
    "density_10_probes_8": (
        "swept, 10 per variable, 8 probes",
        partial(
            run_swept, "density_10_probes_8", n_subdivisions=10, n_parallel_points=8
        ),
    ),
    "density_10_ceiling_30": (
        "swept, 10 per variable, ladder up to 30",
        partial(run_swept, "density_10_ceiling_30", n_subdivisions=10, max_value=30.0),
    ),
    "density_10_probes_16": (
        "swept, 10 per variable, 16 probes",
        partial(
            run_swept,
            "density_10_probes_16",
            n_subdivisions=10,
            n_parallel_points=16,
        ),
    ),
    "random_box": (
        "random box in the trust region",
        partial(run_ablation, "random_box"),
    ),
    "zero_slopes": ("slopes set to zero", partial(run_ablation, "zero_slopes")),
    "random_slopes": (
        "slopes drawn at random",
        partial(run_ablation, "random_slopes"),
    ),
    "density_10_euclidean_diameter": (
        "swept, 10 per variable, Euclidean, diameter",
        partial(
            run_swept,
            "density_10_euclidean_diameter",
            n_subdivisions=10,
            trust_region=EUCLIDEAN_DIAMETER,
        ),
    ),
    "density_10_euclidean_nearest": (
        "swept, 10 per variable, Euclidean, nearest box",
        partial(
            run_swept,
            "density_10_euclidean_nearest",
            n_subdivisions=10,
            trust_region=EUCLIDEAN_NEAREST,
        ),
    ),
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
