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
"""Sweep each mechanism of the master, separately.

The two mechanisms are not combined, see :mod:`benchmarks.configurations`, so
they are swept apart: the constant of the pure convexification on one side, the
convexity margin and the number of parallel points of the adaptive repair on the
other.

The sweep also reports the number of **distinct boxes** whose sub-problem was
solved, which is what the exploration amounts to, and which tells a run that
found the optimum quickly from a run that stopped early.

```shell
python -m benchmarks.tune_convexification
```
"""

from __future__ import annotations

import logging

from gemseo_bilevel_outer_approximation.algos.opt.bilevel_master_outer_approximation.bilevel_master_outer_approximation_settings import (  # noqa: E501
    BILEVEL_MASTER_OUTER_APPROXIMATION_Settings,
)
from numpy import median
from numpy.random import default_rng

from benchmarks.configurations import TRUST_REGION_RADIUS
from benchmarks.problems import RASTRIGIN_LOWER_BOUND
from benchmarks.problems import RASTRIGIN_UPPER_BOUND
from benchmarks.test_outer_approximation_vs_enumeration import GLOBAL_OPTIMUM
from benchmarks.test_outer_approximation_vs_enumeration import _create_scenario
from benchmarks.test_outer_approximation_vs_enumeration import _run_enumeration

CONSTANTS = (0.0, 10.0, 20.0, 30.0, 50.0, 75.0, 100.0, 150.0, 200.0, 300.0)
"""The constants of the pure convexification to sweep.

The range stops at a few hundred on purpose. The constant is of the order of the
variation of the objective over the design space, about eighty here, and beyond
that order it buys nothing: every unexplored box outranks the incumbent whatever
the cuts say. Values such as $10^4$ only make the result decay while costing the
same, since the run ends on the trust region or on the stall counter rather than
on its optimality test.
"""

MARGINS = (0.0, 1.0, 10.0, 30.0, 100.0, 300.0)
"""The convexity margins of the adaptive repair to sweep.

The margin is an absolute quantity in the units of the objective, which spans
about eighty on this benchmark, so the range has to reach that order.
"""

PARALLEL_POINTS = (1, 4, 8)
"""The numbers of parallel points to sweep."""

TOLERANCE = 1e-3
"""The tolerance under which the global optimum is considered reached."""


def measure(
    formulation: str, starting_points, **settings
) -> tuple[int, float, int, int]:
    """Measure one configuration of the master.

    Args:
        formulation: Either ``"constraint"`` or ``"normalized"``.
        starting_points: The starting points.
        **settings: The settings of the master.

    Returns:
        The number of starting points from which the optimum is reached, the
        worst objective value, the median number of solved boxes and the median
        number of evaluations of the objective.
    """
    values = []
    boxes = []
    evaluations = []
    for starting_point in starting_points:
        scenario, _, objective = _create_scenario(starting_point, formulation)
        scenario.execute(
            BILEVEL_MASTER_OUTER_APPROXIMATION_Settings(
                max_iter=200, ub_tol=1e-4, **settings
            )
        )
        values.append(float(scenario.optimization_result.f_opt))
        boxes.append(len(scenario.formulation.optimization_problem.database))
        evaluations.append(objective.n_executions)

    return (
        sum(value <= GLOBAL_OPTIMUM + TOLERANCE for value in values),
        max(values),
        int(median(boxes)),
        int(median(evaluations)),
    )


def main(n_starting_points: int = 8, seed: int = 11) -> None:
    """Sweep both mechanisms of the master.

    Args:
        n_starting_points: The number of starting points per configuration.
        seed: The seed of the starting points.
    """
    logging.disable(logging.CRITICAL)
    rng = default_rng(seed)
    starting_points = [
        rng.uniform(RASTRIGIN_LOWER_BOUND, RASTRIGIN_UPPER_BOUND, 2)
        for _ in range(n_starting_points)
    ]
    header = (
        f"{'reached':>9} {'worst':>9} {'boxes':>7} {'of enum':>8}"
        f" {'evaluations':>12} {'of enum':>8}"
    )
    _, enumerated_boxes, enumerated_evaluations = _run_enumeration(
        starting_points[0], "normalized"
    )
    _create_scenario(starting_points[0], "normalized")[1]

    def report(label: str, reached, worst, boxes, evaluations) -> None:
        """Print one row of a sweep, with the cost against the enumeration.

        Args:
            label: The left-hand column of the row.
            reached: The number of starting points from which the optimum is
                reached.
            worst: The worst objective value.
            boxes: The median number of solved boxes.
            evaluations: The median number of evaluations.
        """
        print(
            f"{label} {reached:>4d}/{n_starting_points:<4d} {worst:>9.4f}"
            f" {boxes:>7d} {boxes / enumerated_boxes:>7.0%}"
            f" {evaluations:>12d} {evaluations / enumerated_evaluations:>7.0%}"
        )

    print(
        "PURE CONVEXIFICATION, adapt off, one parallel point,\n"
        f"trust region of {TRUST_REGION_RADIUS} components changed\n"
        f"{'constant':>10} {header}"
    )
    for constant in CONSTANTS:
        report(
            f"{constant:>10g}",
            *measure(
                "normalized",
                starting_points,
                adapt=False,
                min_dfk=0.0,
                convexification_constant=constant,
                number_of_parallel_points=1,
                max_step=TRUST_REGION_RADIUS,
            ),
        )

    print(
        "\nADAPTIVE REPAIR, no convexification constant\n"
        f"{'margin':>10} {'points':>7} {header}"
    )
    for points in PARALLEL_POINTS:
        for margin in MARGINS:
            reached, worst, boxes, evaluations = measure(
                "normalized",
                starting_points,
                adapt=True,
                min_dfk=margin,
                convexification_constant=0.0,
                number_of_parallel_points=points,
            )
            report(f"{margin:>10g} {points:>7d}", reached, worst, boxes, evaluations)


if __name__ == "__main__":
    main()
