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
r"""A Euclidean trust region for the master, against the Hamming one.

The master restricts each iteration to the boxes within ``max_step`` components
changed of the incumbent, a Hamming distance between one-hot encodings. This
module replaces it by the Euclidean distance between the **centre** of the
incumbent box and the centre of the candidate box.

With $\alpha_{j,k}$ the binary selecting interval $k$ of component $j$, $c_{j,k}$
the centre of that interval and $\bar c_j$ the centre of the incumbent interval of
component $j$, the squared distance is

$$
d^2(\alpha) = \sum_j \sum_k \alpha_{j,k} \, (c_{j,k} - \bar c_j)^2,
$$

which is **linear** in $\alpha$, since exactly one $\alpha_{j,k}$ is one per
component. The trust region $d^2(\alpha) \le R^2$ is therefore a single linear
constraint of the mixed-integer master, like the one it replaces.

Normalization
: The centres are expressed in the design space scaled to $[0, 1]^n$, so that the
  region covers the same fraction of every component whatever its bounds and its
  density, and the radii are given in units of the **coarsest** interval width,
  $h = 1 / \min_j m_j$. A step to the face neighbour of the coarsest component
  then costs one, and a step to the face neighbour of a finer component less than
  one, which is what a geometric ball does. With equal densities, the only case
  this package builds today, it coincides with counting intervals per component,
  ``normalization="interval"``, which is kept for comparison and which charges
  one per interval whatever the density, so that a finer component would be
  given a geometrically smaller reach.

Radius schedule
: Every radius is a setting of :class:`.EuclideanTrustRegion`: the initial
  radius, the floor it shrinks to, the ceiling it grows to, the factors of both
  and the width of the border that triggers a growth. The defaults keep the
  master's own schedule, a shrink of $0.7$ after three stalled iterations and a
  growth of $1.2$ when a step reaches the border, and the floor is one interval
  width, so that the smallest region still admits the face neighbours. The
  parallel probes keep the master's ``geomspace(max(R / 2, R_min), R)``, now in
  Euclidean units: at the initial radius of two, from the face neighbours to the
  boxes two widths away.

Elimination and infeasibility
: The built-in constraint is made vacuous by setting every catalogue weight to
  zero, and the Euclidean one is added to both problems the master builds: the
  mixed-integer problem, at the radius of the probe, and the relaxed problem it
  falls back on when that one is infeasible, at the radius of the master, as the
  built-in constraint does. The elimination of the boxes already solved is left
  to the master, unchanged, so that a ball emptied by the elimination makes the
  master infeasible exactly as an emptied Hamming region does.

```shell
python -m benchmarks.euclidean_trust_region c5 hamming hamming1 1.5 2 3 5
python -m benchmarks.euclidean_trust_region c6 hamming 1.5 2 3 5
python -m benchmarks.euclidean_trust_region table6 hamming 1.5 2
```

The results are Tables C.11 to C.13 of the tuning annex: the ball is better on
Rastrigin and Ackley, comparable on Griewank, and fails on Styblinski-Tang, whose
basins lie five intervals apart and are joined by one Hamming step only.

The change belongs upstream, in ``OuterApproximationOptimizer`` of
``gemseo-bilevel-outer-approximation``; see ``UPSTREAM_PATCH``.
"""

from __future__ import annotations

import argparse
import logging
from contextlib import contextmanager
from contextlib import suppress
from dataclasses import dataclass
from math import isfinite
from math import sqrt
from statistics import median
from typing import TYPE_CHECKING
from typing import Any

from gemseo.core.mdo_functions.mdo_function import MDOFunction
from gemseo.core.mdo_functions.mdo_linear_function import MDOLinearFunction
from gemseo_bilevel_outer_approximation.algos.opt.core import (
    outer_approximation_optimizer as core,
)
from numpy import arange
from numpy import argmax
from numpy import concatenate
from numpy import ones
from numpy import zeros

from benchmarks.baselines import BudgetedCounter
from benchmarks.baselines import BudgetExceededError
from benchmarks.baselines import _design_space
from benchmarks.baselines import _result
from benchmarks.baselines import _starting_point
from benchmarks.baselines import run_box_subdivision
from benchmarks.configurations import CONFIGURATIONS
from benchmarks.configurations import DEFAULT_CONFIGURATION
from benchmarks.configurations import TRUST_REGION_RADIUS
from benchmarks.problems import PROBLEMS
from benchmarks.problems import Objective
from gemseo_box_subdivision import BoxSubdivisionScenario
from gemseo_box_subdivision import SweptBoxSubdivisionSettings

if TYPE_CHECKING:
    from collections.abc import Iterator
    from collections.abc import Sequence

    from numpy import ndarray

    from benchmarks.baselines import Result
    from benchmarks.problems import Problem

NORMALIZATIONS = ("unit_cube", "interval")
"""The coordinates the centres of the boxes are expressed in."""

_OPTIMIZER = core.OuterApproximationOptimizer
"""The master, whose private methods are mangled under its own name."""

_PATCHED = (
    "_build_milp_problem",
    "_build_relaxed_milp_problem",
    "_OuterApproximationOptimizer__iterate",
    "_OuterApproximationOptimizer__decrease_step_size",
    "_OuterApproximationOptimizer__increase_step_size",
    "_OuterApproximationOptimizer__check_trust_region_border",
)
"""The methods of the master the Euclidean trust region replaces or wraps."""


@dataclass(frozen=True)
class EuclideanTrustRegion:
    """The settings of the Euclidean trust region, in units of interval width.

    A width is that of the coarsest interval, in the design space scaled to the
    unit hypercube, see :data:`.NORMALIZATIONS`.
    """

    initial_radius: float = 2.0
    """The radius of the first iteration, and of every iteration until a shrink."""

    min_radius: float = 1.0
    """The floor of the radius, one width so that the face neighbours stay in."""

    max_radius: float = 0.0
    """The ceiling of the radius when it grows, or zero for the initial radius,
    which is the master's own rule."""

    shrink_factor: float = 0.7
    """The factor applied to the radius after stalled iterations."""

    growth_factor: float = 1.2
    """The factor applied to the radius when a step reaches its border."""

    border_width: float = 1.0
    """How close to the radius a step has to land to count as on the border.

    The Hamming region counts a step changing ``floor(radius)`` components as on
    its border, a width of one component; the Euclidean one keeps one width.
    """

    normalization: str = "unit_cube"
    """The coordinates of the centres, one of :data:`.NORMALIZATIONS`."""

    def __post_init__(self) -> None:
        """Check the settings.

        Raises:
            ValueError: When a radius or a factor is out of range, or when the
                normalization is unknown.
        """
        if self.normalization not in NORMALIZATIONS:
            msg = f"The normalization must be one of {NORMALIZATIONS}."
            raise ValueError(msg)

        if not 0 < self.min_radius <= self.initial_radius:
            msg = "The radii must satisfy 0 < min_radius <= initial_radius."
            raise ValueError(msg)

        if self.max_radius and self.max_radius < self.initial_radius:
            msg = "The maximum radius must not be below the initial radius."
            raise ValueError(msg)

        if not 0 < self.shrink_factor < 1 or self.growth_factor < 1:
            msg = "The radius must shrink by a factor below one and grow above it."
            raise ValueError(msg)

    @property
    def ceiling(self) -> float:
        """The largest radius the region grows to."""
        return self.max_radius or self.initial_radius


def blocks_of(optimizer: Any) -> list[int]:
    """Return the number of intervals of each component, in one-hot order.

    Args:
        optimizer: The master.

    Returns:
        One entry per component of every categorical variable.
    """
    return [
        optimizer.n_catalogues[name]
        for name in optimizer.design_space.categorical_variables
        for _ in range(optimizer.n_members[name])
    ]


def _scales(blocks: Sequence[int], normalization: str) -> list[float]:
    """Return the width of an interval of each component, in reference widths.

    Args:
        blocks: The number of intervals of each component.
        normalization: One of :data:`.NORMALIZATIONS`.

    Returns:
        The width of one interval of each component.
    """
    if normalization == "interval":
        return [1.0] * len(blocks)

    coarsest = min(blocks)
    return [coarsest / size for size in blocks]


def squared_distance_coefficients(
    blocks: Sequence[int], incumbent: ndarray, normalization: str = "unit_cube"
) -> ndarray:
    r"""Return the coefficients of $d^2(\alpha)$ around an incumbent box.

    Args:
        blocks: The number of intervals of each component, in one-hot order.
        incumbent: The one-hot encoding of the incumbent box.
        normalization: One of :data:`.NORMALIZATIONS`.

    Returns:
        The vector $(c_{j,k} - \bar c_j)^2$, so that its dot product with the
        one-hot encoding of a candidate is the squared distance between the
        centres, in squared reference widths.
    """
    coefficients = []
    offset = 0
    for size, scale in zip(blocks, _scales(blocks, normalization), strict=True):
        selected = int(argmax(incumbent[offset : offset + size]))
        coefficients.append(((arange(size) - selected) * scale) ** 2)
        offset += size

    return concatenate(coefficients)


def box_distance(
    blocks: Sequence[int],
    first: ndarray,
    second: ndarray,
    normalization: str = "unit_cube",
) -> float:
    """Return the distance between the centres of two boxes.

    Args:
        blocks: The number of intervals of each component, in one-hot order.
        first: The one-hot encoding of a box.
        second: The one-hot encoding of another box.
        normalization: One of :data:`.NORMALIZATIONS`.

    Returns:
        The distance, in reference widths.
    """
    coefficients = squared_distance_coefficients(blocks, first, normalization)
    return sqrt(max(float(coefficients @ second[: coefficients.size]), 0.0))


_TOLERANCE = 1e-9
"""The slack of the constraint, so that a box exactly on the sphere stays in."""


def _add_ball(
    optimizer: Any,
    problem: Any,
    incumbent: ndarray,
    radius: float,
    region: EuclideanTrustRegion,
    n_extra: int,
) -> None:
    """Add the Euclidean trust region to a problem of the master.

    Args:
        optimizer: The master.
        problem: The problem the master has built.
        incumbent: The one-hot encoding of the incumbent box.
        radius: The radius, in reference widths.
        region: The settings of the trust region.
        n_extra: The number of continuous variables after the binaries.
    """
    coefficients = squared_distance_coefficients(
        blocks_of(optimizer), incumbent, region.normalization
    )
    names = ["alpha", "eta", "delta"][: 1 + n_extra]
    problem.add_constraint(
        MDOLinearFunction(
            concatenate([coefficients, zeros(n_extra)]),
            "euclidean trust region",
            input_names=names,
            expr="",
        ),
        value=float(radius) ** 2 + _TOLERANCE,
        constraint_type=MDOFunction.ConstraintType.INEQ,
    )


@contextmanager
def euclidean_trust_region(
    region: EuclideanTrustRegion | None = None,
) -> Iterator[EuclideanTrustRegion]:
    """Replace the trust region of the master by a Euclidean ball.

    The radius the master carries, ``current_step``, is read as a radius in
    reference widths, and the schedule driving it is the one of ``region``,
    whatever ``max_step`` and ``min_step`` the master was given.

    The built-in constraint is left in place and made vacuous by the weights of
    the design space, which this context manager does not set: build the design
    space with weights at zero.

    Args:
        region: The settings of the trust region, or ``None`` for the defaults.

    Yields:
        The settings of the trust region.
    """
    region = region or EuclideanTrustRegion()
    originals = {name: getattr(_OPTIMIZER, name) for name in _PATCHED}

    def build(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        problem = originals["_build_milp_problem"](self, *args, **kwargs)
        incumbent = kwargs.get("retained_alpha", args[-2] if len(args) > 1 else None)
        radius = kwargs.get("current_step", args[-1] if args else None)
        if incumbent is not None and radius is not None:
            _add_ball(self, problem, incumbent, radius, region, 1)

        return problem

    def build_relaxed(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        problem = originals["_build_relaxed_milp_problem"](self, *args, **kwargs)
        incumbent = kwargs.get("retained_alpha", args[-1] if args else None)
        if incumbent is not None:
            # As the built-in constraint, at the radius of the master and not at
            # the radius of the probe that turned out infeasible.
            _add_ball(self, problem, incumbent, self.current_step, region, 2)

        return problem

    def iterate(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        self.max_step = region.initial_radius
        self.min_step = region.min_radius
        return originals["_OuterApproximationOptimizer__iterate"](self, *args, **kwargs)

    def decrease(self) -> None:  # noqa: ANN001
        self.current_step = max(
            self.current_step * region.shrink_factor, region.min_radius
        )

    def increase(self) -> None:  # noqa: ANN001
        self.current_step = min(
            self.current_step * region.growth_factor, region.ceiling
        )

    def on_border(self, alpha, alphaold) -> bool:  # noqa: ANN001
        distance = box_distance(blocks_of(self), alphaold, alpha, region.normalization)
        return self.current_step - distance < region.border_width

    replacements = dict(
        zip(
            _PATCHED,
            (build, build_relaxed, iterate, decrease, increase, on_border),
            strict=True,
        )
    )
    for name, replacement in replacements.items():
        setattr(_OPTIMIZER, name, replacement)

    try:
        yield region
    finally:
        for name, original in originals.items():
            setattr(_OPTIMIZER, name, original)


def run(  # noqa: PLR0913
    problem: Problem,
    dimension: int,
    seed: int,
    budget: int,
    n_subdivisions: int,
    region: EuclideanTrustRegion | int = TRUST_REGION_RADIUS,
    swept: bool = False,
) -> Result:
    """Run the method with either trust region.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the starting point.
        budget: The budget in equivalent objective evaluations.
        n_subdivisions: The number of subdivisions per variable.
        region: The Euclidean trust region, or the radius of the Hamming one
            with unit weights, which is what the package does with
            :data:`.TRUST_REGION_RADIUS`.
        swept: Whether the convexity is swept rather than calibrated.

    Returns:
        The outcome of the run.
    """
    if not isinstance(region, EuclideanTrustRegion):
        weights = ones(n_subdivisions)
        return _run(
            problem, dimension, seed, budget, n_subdivisions, weights, swept, region
        )

    # The radius given to the master is ignored, the region driving its own.
    weights = zeros(n_subdivisions)
    with euclidean_trust_region(region):
        return _run(problem, dimension, seed, budget, n_subdivisions, weights, swept)


def _run(  # noqa: PLR0913
    problem: Problem,
    dimension: int,
    seed: int,
    budget: int,
    n_subdivisions: int,
    weights: ndarray,
    swept: bool,
    radius: int = TRUST_REGION_RADIUS,
) -> Result:
    """Run the method with given catalogue weights.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the starting point.
        budget: The budget in equivalent objective evaluations.
        n_subdivisions: The number of subdivisions per variable.
        weights: The catalogue weights of the subdivisions.
        swept: Whether the convexity is swept rather than calibrated.
        radius: The radius given to the master, ``max_step``.

    Returns:
        The outcome of the run.
    """
    if not swept:
        return run_box_subdivision(
            problem,
            dimension,
            seed,
            budget,
            adjoint=True,
            n_subdivisions=n_subdivisions,
            overrides={"max_step": radius},
            weights=weights,
        )

    # As :func:`.run_swept_box_subdivision`, with the weights of the design
    # space passed through.
    counter = BudgetedCounter(problem, dimension, budget, True)
    scenario = BoxSubdivisionScenario(
        [Objective(counter, dimension)],
        "f",
        _design_space(problem, dimension, _starting_point(problem, dimension, seed)),
        n_subdivisions=n_subdivisions,
        weights={"x": weights},
        settings=SweptBoxSubdivisionSettings(
            trust_region_radius=radius,
            n_parallel_points=CONFIGURATIONS[DEFAULT_CONFIGURATION][
                "number_of_parallel_points"
            ],
            max_iter=10000,
            tolerance=1e-4,
        ),
    )
    with suppress(BudgetExceededError, KeyError):
        scenario.execute()

    return _result("box_subdivision_swept", problem, dimension, seed, counter, True)


SETTINGS = {
    "c5": (2, 1000, (11, 101, 202, 303, 404, 505, 606, 707), False),
    "c6": (5, 2500, (11, 101, 202), False),
    "table6": (5, 2500, (11, 101, 202, 303, 404), True),
}
"""The dimension, budget, seeds and sweep of each experiment, by name."""

PROBLEM_NAMES = {
    "c5": ("rastrigin", "ackley", "griewank"),
    "c6": ("rastrigin", "ackley", "styblinski_tang", "griewank"),
    "table6": ("rastrigin", "ackley", "styblinski_tang", "griewank"),
}
"""The problems of each experiment."""

N_SUBDIVISIONS = 10
"""The number of subdivisions per variable."""

TOLERANCE = 1e-4
"""The distance under which the optimum is reached, as in Table C.5."""


def cell(gaps: Sequence[float], costs: Sequence[int]) -> str:
    """Return a cell of the documentation tables.

    Args:
        gaps: The distances to the optimum of the runs.
        costs: The costs of the runs.

    Returns:
        The median distance, the median cost and the starting points reaching
        the optimum.
    """
    if not gaps:
        return "failed"

    reached = sum(gap <= TOLERANCE for gap in gaps)
    gap = median(gaps)
    distance = f"{gap:.3f}" if isfinite(gap) else "inf"
    return f"${distance}$ · {median(costs):.0f} · {reached}/{len(gaps)}"


def main(argv: Sequence[str] | None = None) -> None:
    """Compare the two trust regions on one experiment.

    Args:
        argv: The command line, ``EXPERIMENT [hamming[RADIUS] | RADIUS ...]``,
            ``hamming`` alone for :data:`.TRUST_REGION_RADIUS` and a bare number
            for the initial radius of the Euclidean region.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", choices=SETTINGS)
    parser.add_argument("regions", nargs="*", default=["hamming", "2"])
    parser.add_argument("--normalization", default="unit_cube")
    parser.add_argument("--problems", nargs="*", default=())
    arguments = parser.parse_args(argv)
    dimension, budget, seeds, swept = SETTINGS[arguments.experiment]
    logging.disable(logging.CRITICAL)
    for label in arguments.regions:
        region = (
            int(label.removeprefix("hamming") or TRUST_REGION_RADIUS)
            if label.startswith("hamming")
            else EuclideanTrustRegion(
                initial_radius=float(label), normalization=arguments.normalization
            )
        )
        cells = []
        for name in arguments.problems or PROBLEM_NAMES[arguments.experiment]:
            benchmark = PROBLEMS[name]
            optimum = benchmark.optimum(dimension)
            gaps = []
            costs = []
            for seed in seeds:
                outcome = run(
                    benchmark, dimension, seed, budget, N_SUBDIVISIONS, region, swept
                )
                gaps.append(outcome.gap(optimum))
                costs.append(outcome.cost_adjoint)
                print(f"# {label} {name} {seed} {gaps[-1]:.4g} {costs[-1]}", flush=True)  # noqa: T201

            cells.append(cell(gaps, costs))

        print(f"| {label} | " + " | ".join(cells) + " |", flush=True)  # noqa: T201

    logging.disable(logging.NOTSET)


UPSTREAM_PATCH = r"""
In ``OuterApproximationOptimizer`` (core/outer_approximation_optimizer.py):

1. settings: ``max_step`` and ``min_step`` become ``PositiveFloat``, and a new
   ``trust_region_metric: Literal["hamming", "euclidean"] = "hamming"`` is read
   in ``optimize``, with ``step_shrink_factor = 0.7`` and
   ``step_growth_factor = 1.2`` replacing the literals of
   ``__decrease_step_size`` and ``__increase_step_size``.
2. a method ``_trust_region_row(retained_alpha) -> (a, b, positive)``: for
   "hamming" the current ``(weights * retained_alpha, sum - step, True)``; for
   "euclidean" ``a = concatenate([((arange(m) - k_j) * m_min / m) ** 2 ...])``
   per component, ``b = step ** 2``, ``positive=False``.
3. "Constraint E" of ``_build_milp_problem`` and the trust region of
   ``_build_relaxed_milp_problem`` build their row from it, padded with one and
   two zeros.
4. ``__check_trust_region_border`` compares ``current_step`` with the distance
   of the metric, ``sqrt(a(alphaold) @ alpha)`` for "euclidean".
"""
"""The change this module makes by patching, as it would be made upstream."""


if __name__ == "__main__":
    main()
