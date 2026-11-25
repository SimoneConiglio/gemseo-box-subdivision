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

The trust region itself is the option ``trust_region_metric="euclidean"`` of the
settings, implemented in :mod:`gemseo_box_subdivision._euclidean_trust_region`;
this module holds the experiments.
"""

from __future__ import annotations

import argparse
import logging
from contextlib import suppress
from math import isfinite
from statistics import median
from typing import TYPE_CHECKING

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
from gemseo_box_subdivision._euclidean_trust_region import EuclideanTrustRegion
from gemseo_box_subdivision._euclidean_trust_region import euclidean_trust_region

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy import ndarray

    from benchmarks.baselines import Result
    from benchmarks.problems import Problem


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
    "d12": (5, 0, (11, 101, 202), True),
}
"""The dimension, budget, seeds and sweep of each experiment, by name."""

PROBLEM_NAMES = {
    "c5": ("rastrigin", "ackley", "griewank"),
    "c6": ("rastrigin", "ackley", "styblinski_tang", "griewank"),
    "table6": ("rastrigin", "ackley", "styblinski_tang", "griewank"),
    "d12": ("styblinski_tang", "partly_multimodal", "ackley", "griewank", "rastrigin"),
}
"""The problems of each experiment."""

DENSITIES = {
    "styblinski_tang": (2,) * 5,
    "partly_multimodal": (10, 10, 1, 1, 1),
    "ackley": (10,) * 5,
    "griewank": (19, 13, 11, 7, 9),
    "rastrigin": (10,) * 5,
}
"""The densities of Table D.12, estimated by counting basins, by problem.

Each run is granted four times the budget the density predicts, forty
evaluations per binary, as in that table."""

D12_TOLERANCE = 1e-2
"""The distance under which the optimum is reached in Table D.12."""


def run_at_density(
    problem: Problem,
    density: Sequence[int],
    seed: int,
    region: EuclideanTrustRegion | int = TRUST_REGION_RADIUS,
) -> tuple[float, int]:
    """Run the swept configuration at a density per component, as Table D.12.

    Args:
        problem: The problem, in five variables.
        density: The number of subdivisions of each component.
        seed: The seed of the starting point.
        region: The Euclidean trust region, or the radius of the Hamming one.

    Returns:
        The distance to the optimum and the cost.
    """
    from benchmarks.basin_spacing import COST_PER_SUB_PROBLEM
    from benchmarks.basin_spacing import HEADROOM
    from benchmarks.basin_spacing import run_at_density_swept

    budget = sum(density) * COST_PER_SUB_PROBLEM * HEADROOM
    dimension = len(density)
    if isinstance(region, EuclideanTrustRegion):
        with euclidean_trust_region(region):
            outcome = run_at_density_swept(problem, dimension, density, seed, budget)
    else:
        outcome = run_at_density_swept(problem, dimension, density, seed, budget)

    return outcome.best - problem.optimum(dimension), outcome.cost


N_SUBDIVISIONS = 10
"""The number of subdivisions per variable."""

TOLERANCE = 1e-4
"""The distance under which the optimum is reached, as in Table C.5."""


def cell(
    gaps: Sequence[float], costs: Sequence[int], tolerance: float = TOLERANCE
) -> str:
    """Return a cell of the documentation tables.

    Args:
        gaps: The distances to the optimum of the runs.
        costs: The costs of the runs.
        tolerance: The distance under which the optimum is reached.

    Returns:
        The median distance, the median cost and the starting points reaching
        the optimum.
    """
    if not gaps:
        return "failed"

    reached = sum(gap <= tolerance for gap in gaps)
    gap = median(gaps)
    distance = f"{gap:.3f}" if isfinite(gap) else "inf"
    return f"${distance}$ · {median(costs):.0f} · {reached}/{len(gaps)}"


def main(argv: Sequence[str] | None = None) -> None:
    """Compare the two trust regions on one experiment.

    Args:
        argv: The command line,
            ``EXPERIMENT [hamming[RADIUS] | RADIUS | diameter ...]``, ``hamming``
            alone for :data:`.TRUST_REGION_RADIUS`, a bare number for the initial
            radius of the Euclidean region, ``diameter`` for its diameter
            schedule, and ``nearestRADIUS`` or ``nearest-diameter`` for the same
            regions measured from the nearest evaluated box.
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
        if label.startswith("hamming"):
            region = int(label.removeprefix("hamming") or TRUST_REGION_RADIUS)
        elif label in {"diameter", "nearest-diameter"}:
            region = EuclideanTrustRegion(
                schedule="diameter",
                normalization=arguments.normalization,
                anchor="nearest" if label.startswith("nearest") else "incumbent",
            )
        elif label.startswith("nearest"):
            region = EuclideanTrustRegion(
                initial_radius=float(label.removeprefix("nearest")),
                normalization=arguments.normalization,
                anchor="nearest",
            )
        else:
            region = EuclideanTrustRegion(
                initial_radius=float(label), normalization=arguments.normalization
            )

        cells = []
        for name in arguments.problems or PROBLEM_NAMES[arguments.experiment]:
            benchmark = PROBLEMS[name]
            optimum = benchmark.optimum(dimension)
            gaps = []
            costs = []
            for seed in seeds:
                if arguments.experiment == "d12":
                    gap, cost = run_at_density(benchmark, DENSITIES[name], seed, region)
                else:
                    outcome = run(
                        benchmark,
                        dimension,
                        seed,
                        budget,
                        N_SUBDIVISIONS,
                        region,
                        swept,
                    )
                    gap, cost = outcome.gap(optimum), outcome.cost_adjoint

                gaps.append(gap)
                costs.append(cost)
                print(f"# {label} {name} {seed} {gaps[-1]:.4g} {costs[-1]}", flush=True)  # noqa: T201

            tolerance = D12_TOLERANCE if arguments.experiment == "d12" else TOLERANCE
            cells.append(cell(gaps, costs, tolerance))

        print(f"| {label} | " + " | ".join(cells) + " |", flush=True)  # noqa: T201

    logging.disable(logging.NOTSET)


if __name__ == "__main__":
    main()
