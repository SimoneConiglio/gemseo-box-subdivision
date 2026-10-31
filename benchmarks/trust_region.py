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
r"""What the trust region of the master measures, and what it should.

The master restricts each iteration to a neighbourhood of the incumbent box with

$$
\sum_{j \,:\, \alpha'_j = \alpha_j} w_j(\alpha)
\ \ge\ \sum_j w_j(\alpha) - \texttt{max\_step},
$$

whose coefficient vector is $w \odot \alpha$, the weights of the **incumbent**.
The cost of a move is therefore the sum of the weights the incumbent holds on the
components the candidate changes, and it never reads what the candidate changes
them *to*.

For a **nominal** catalogue, a set of unordered alternatives, that is the right
thing with unit weights: the distance is then the number of components changed, a
Hamming distance, and no notion of proximity exists to express. For an **ordinal**
catalogue, which is what the index of a subdivision is, it is not a proximity at
all: leaving subdivision $0$ is free whatever the candidate moves to, and leaving
subdivision $m-1$ costs $m-1$ even to move next door.

What an ordinal catalogue calls for is the difference of the **selected values**,

$$
\left| v^\top \alpha'_j - v^\top \alpha_j \right| \le \texttt{max\_step}
\quad \text{for every component } j,
$$

which is linear in $\alpha'$ and needs two constraints per component, since
$v^\top \alpha_j$ is a constant once the incumbent is known. This module adds
them to the problem the master builds, and compares:

`indexes`
: the weights left to the catalogue values, which is what the package does today.

`unit`
: every weight at one, so proximity is ignored and the distance counts the
  components changed.

`none`
: every weight at zero, which makes the built-in constraint vacuous and removes
  the trust region altogether.

`proximity`
: the built-in constraint removed as above, and the difference of the selected
  values bounded instead, per component.

```shell
python -m benchmarks.trust_region
```
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextlib import suppress
from statistics import median
from typing import TYPE_CHECKING

from gemseo.core.function.array_function import ArrayFunction
from gemseo.core.function.linear_function import LinearFunction
from gemseo_bilevel_outer_approximation.algos.opt.core import (
    outer_approximation_optimizer as core,
)
from numpy import arange
from numpy import ones
from numpy import zeros

from benchmarks.baselines import run_box_subdivision
from benchmarks.problems import PROBLEMS

if TYPE_CHECKING:
    from collections.abc import Iterator

DIMENSION = 5
"""The number of design variables."""

BUDGET = 2500
"""The budget in equivalent objective evaluations."""

SEEDS = (11, 101, 202, 303, 404, 505)
"""The seeds of the starting points."""

N_SUBDIVISIONS = 10
"""The number of subdivisions per variable."""


def _add_proximity_constraints(optimizer, problem, retained_alpha, step) -> None:  # noqa: ANN001
    """Bound the difference of the selected catalogue values, per component.

    Args:
        optimizer: The master.
        problem: The problem the master has built.
        retained_alpha: The one-hot encoding of the incumbent box.
        step: The largest difference of index allowed, per component.
    """
    names = ["alpha", "eta"]
    size = retained_alpha.size
    offset = 0
    for name in optimizer.design_space.categorical_variables:
        n_catalogues = optimizer.n_catalogues[name]
        # The catalogues of this package are the ranges of the subdivisions, so
        # the value a slot selects is its position.
        values = arange(n_catalogues, dtype=float)
        for member in range(optimizer.n_members[name]):
            coefficients = zeros(size + 1)
            coefficients[offset : offset + n_catalogues] = values
            selected = float(values @ retained_alpha[offset : offset + n_catalogues])
            for sign, bound in ((1.0, selected + step), (-1.0, step - selected)):
                problem.add_constraint(
                    LinearFunction(
                        sign * coefficients,
                        f"proximity {name} {member} {'up' if sign > 0 else 'down'}",
                        input_names=names,
                        expr="",
                    ),
                    value=bound,
                    constraint_type=ArrayFunction.ConstraintType.INEQ,
                )

            offset += n_catalogues


@contextmanager
def proximity_trust_region() -> Iterator[None]:
    """Replace the trust region of the master by a bound on the index moved.

    The built-in constraint is left in place and made vacuous by the weights of
    the design space, which this context manager does not set: build the design
    space with weights at zero.
    """
    original = core.OuterApproximationOptimizer._build_milp_problem

    def patched(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        problem = original(self, *args, **kwargs)
        retained_alpha = kwargs.get("retained_alpha", args[-2] if args else None)
        step = kwargs.get("current_step", args[-1] if args else None)
        if retained_alpha is not None and step is not None:
            _add_proximity_constraints(self, problem, retained_alpha, step)

        return problem

    core.OuterApproximationOptimizer._build_milp_problem = patched
    try:
        yield
    finally:
        core.OuterApproximationOptimizer._build_milp_problem = original


def weights_of(kind: str, n_subdivisions: int):  # noqa: ANN201
    """Return the catalogue weights of a metric.

    Args:
        kind: The metric, ``"indexes"``, ``"unit"``, ``"none"`` or
            ``"proximity"``.
        n_subdivisions: The number of subdivisions per variable.

    Returns:
        The weights, or ``None`` to leave them at the catalogue values.
    """
    if kind == "indexes":
        return None

    if kind == "unit":
        return ones(n_subdivisions)

    return zeros(n_subdivisions)


def run(problem, dimension, seed, budget, kind, n_subdivisions, step):  # noqa: ANN001, ANN201, PLR0913
    """Run the method with one metric for the trust region.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the starting point.
        budget: The budget in equivalent objective evaluations.
        kind: The metric of the trust region.
        n_subdivisions: The number of subdivisions per variable.
        step: The radius of the trust region, in the units of the metric.

    Returns:
        The outcome of the run.
    """
    weights = weights_of(kind, n_subdivisions)
    overrides = {"max_step": step}
    if kind == "proximity":
        with proximity_trust_region():
            return run_box_subdivision(
                problem,
                dimension,
                seed,
                budget,
                adjoint=True,
                n_subdivisions=n_subdivisions,
                overrides=overrides,
                weights=weights,
            )

    return run_box_subdivision(
        problem,
        dimension,
        seed,
        budget,
        adjoint=True,
        n_subdivisions=n_subdivisions,
        overrides=overrides,
        weights=weights,
    )


METRICS = (
    ("indexes, step 45", "indexes", 45),
    ("unit, step 5", "unit", 5),
    ("unit, step 2", "unit", 2),
    ("none", "none", 1),
    ("proximity, step 9", "proximity", 9),
    ("proximity, step 3", "proximity", 3),
)
"""The metrics of the trust region to compare, with their radius."""


def main() -> None:
    """Compare the metrics of the trust region."""
    logging.disable(logging.CRITICAL)
    print(
        f"{DIMENSION} variables, {N_SUBDIVISIONS} subdivisions, budget {BUDGET}, "
        f"median over {len(SEEDS)} starting points\n"
    )
    print(f"{'problem':>18} {'trust region':>22} {'gap':>9} {'cost':>7} {'reached':>8}")
    for name in ("rastrigin", "ackley", "styblinski_tang"):
        benchmark = PROBLEMS[name]
        optimum = benchmark.optimum(DIMENSION)
        for label, kind, step in METRICS:
            gaps = []
            costs = []
            for seed in SEEDS:
                with suppress(Exception):
                    outcome = run(
                        benchmark, DIMENSION, seed, BUDGET, kind, N_SUBDIVISIONS, step
                    )
                    gaps.append(outcome.gap(optimum))
                    costs.append(outcome.cost_adjoint)

            if not gaps:
                print(f"{name:>18} {label:>22} {'failed':>9}")
                continue

            print(
                f"{name:>18} {label:>22} {median(gaps):>9.3f} {median(costs):>7.0f}"
                f" {sum(gap <= 1e-4 for gap in gaps)}/{len(gaps)}"
            )

    logging.disable(logging.NOTSET)


if __name__ == "__main__":
    main()
