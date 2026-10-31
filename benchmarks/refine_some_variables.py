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
"""Subdivide some of the variables only, and leave the rest to the sub-problem.

The number of boxes is the Cartesian product of the subdivisions, so a fine
subdivision of every variable is out of reach as soon as there are a few of them.
Subdividing only some of the variables keeps the product small while resolving
the variables that need it, the others being ordinary variables of the
sub-problem.

Whether that is a good trade depends on **where the multimodality is**. A
variable left unsubdivided keeps all of its basins inside every box, and the
local solve returns the one it starts in, so the exchange is only worth it when
the objective is close to unimodal in the variables left out.

```shell
python -m benchmarks.refine_some_variables
```
"""

from __future__ import annotations

import logging
from contextlib import suppress
from statistics import median
from typing import TYPE_CHECKING

from gemseo import create_scenario
from gemseo.algos.design_space import DesignSpace
from gemseo.core.chains.chain import MDOChain
from gemseo.core.discipline import Discipline
from gemseo.settings.formulations import DisciplinaryOpt_Settings
from gemseo.settings.opt import SLSQP_Settings
from gemseo_bilevel_outer_approximation.algos.opt.bilevel_master_outer_approximation.bilevel_master_outer_approximation_settings import (  # noqa: E501
    BILEVEL_MASTER_OUTER_APPROXIMATION_Settings,
)
from numpy import array
from numpy import atleast_2d
from numpy import concatenate
from numpy import zeros
from numpy.random import default_rng

from benchmarks.baselines import BudgetedCounter
from benchmarks.baselines import BudgetExceededError
from benchmarks.configurations import CONFIGURATIONS
from benchmarks.configurations import DEFAULT_CONFIGURATION
from benchmarks.configurations import TRUST_REGION_RADIUS
from benchmarks.problems import PROBLEMS
from gemseo_box_subdivision.design_spaces import create_normalized_box_design_space
from gemseo_box_subdivision.disciplines.box_mapping import BoxMapping
from gemseo_box_subdivision.subdivisions.box import BoxSubdivision

if TYPE_CHECKING:
    from benchmarks.problems import Problem

SPLIT = "x_split"
"""The name of the subdivided variables."""

FREE = "x_free"
"""The name of the variables left to the sub-problem."""

DIMENSION = 5
"""The number of design variables."""

BUDGET = 2500
"""The budget in equivalent objective evaluations."""

SEEDS = (11, 101, 202)
"""The seeds of the starting points."""

CASES = ((5, 2), (3, 4), (2, 10), (2, 5), (2, 3), (1, 10))
"""The numbers of subdivided variables and of subdivisions of each."""

PROBLEM_NAMES = ("rastrigin", "styblinski_tang", "partly_multimodal")
"""The problems to compare, the last one being multimodal in two variables only."""


class SplitObjective(Discipline):
    """The objective of a problem whose variables are split in two groups."""

    def __init__(self, counter: BudgetedCounter, n_split: int, n_free: int) -> None:
        """
        Args:
            counter: The counter of the calls.
            n_split: The number of subdivided variables.
            n_free: The number of variables left to the sub-problem.
        """  # noqa: D205, D212
        super().__init__()
        self._counter = counter
        self.__n_split = n_split
        data = {SPLIT: zeros(n_split), FREE: zeros(n_free)}
        self.io.input_grammar.update_from_data(data)
        self.io.output_grammar.update_from_data({"f": zeros(1)})
        self.default_input_data = data

    def _run(self, input_data):  # noqa: ANN001, ANN202
        x = concatenate([input_data[SPLIT], input_data[FREE]])
        return {"f": array([self._counter.objective(x)])}

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        x = concatenate([self.io.data[SPLIT], self.io.data[FREE]])
        gradient = self._counter.gradient(x)
        self.jac["f"][SPLIT] = atleast_2d(gradient[: self.__n_split])
        self.jac["f"][FREE] = atleast_2d(gradient[self.__n_split :])


def run(
    problem: Problem,
    dimension: int,
    n_split: int,
    n_subdivisions: int,
    seed: int,
    budget: int,
) -> tuple[float, int]:
    """Run the method subdividing the first variables only.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        n_split: The number of subdivided variables.
        n_subdivisions: The number of subdivisions of each of them.
        seed: The seed of the starting point.
        budget: The budget in equivalent objective evaluations.

    Returns:
        The best objective value and the cost under the adjoint convention.
    """
    counter = BudgetedCounter(problem, dimension, budget, adjoint=True)
    start = default_rng(seed).uniform(
        problem.lower_bound, problem.upper_bound, dimension
    )
    design_space = DesignSpace()
    design_space.add_variable(
        SPLIT,
        lower_bound=problem.lower_bound,
        upper_bound=problem.upper_bound,
        size=n_split,
        value=start[:n_split],
    )
    n_free = dimension - n_split
    if n_free:
        design_space.add_variable(
            FREE,
            lower_bound=problem.lower_bound,
            upper_bound=problem.upper_bound,
            size=n_free,
            value=start[n_split:],
        )

    # Only SPLIT is subdivided: FREE stays an ordinary sub-problem variable.
    subdivision = BoxSubdivision.from_design_space(
        design_space, n_subdivisions, [SPLIT]
    )
    scenario = create_scenario(
        [MDOChain([BoxMapping(subdivision), SplitObjective(counter, n_split, n_free)])],
        "f",
        create_normalized_box_design_space(subdivision, design_space),
        formulation_name="Benders",
        main_problem_design_variables=[f"{SPLIT}_box"],
        sub_problem_algo_settings=SLSQP_Settings(max_iter=40),
        sub_problem_formulation_settings=DisciplinaryOpt_Settings(),
    )
    settings = dict(CONFIGURATIONS[DEFAULT_CONFIGURATION])
    settings["max_step"] = TRUST_REGION_RADIUS
    # A budget spent inside a linearization leaves the discipline without its
    # output, which GEMSEO then reports as a missing key.
    with suppress(BudgetExceededError, KeyError):
        scenario.execute(
            BILEVEL_MASTER_OUTER_APPROXIMATION_Settings(
                max_iter=10000, ub_tol=1e-4, **settings
            )
        )

    return counter.best, counter.cost(dimension, adjoint=True)


def main() -> None:
    """Compare the partial refinements over the problems."""
    logging.disable(logging.CRITICAL)
    print(
        f"{DIMENSION} variables, budget {BUDGET}, "
        f"median over {len(SEEDS)} starting points\n"
    )
    print(
        f"{'problem':>18} {'split':>6} {'m':>3} {'boxes':>7} {'gap':>9}"
        f" {'cost':>7} {'reached':>8}"
    )
    for name in PROBLEM_NAMES:
        problem = PROBLEMS[name]
        optimum = problem.optimum(DIMENSION)
        for n_split, n_subdivisions in CASES:
            gaps = []
            costs = []
            for seed in SEEDS:
                best, cost = run(
                    problem, DIMENSION, n_split, n_subdivisions, seed, BUDGET
                )
                gaps.append(best - optimum)
                costs.append(cost)

            print(
                f"{name:>18} {n_split:>6} {n_subdivisions:>3}"
                f" {n_subdivisions**n_split:>7} {median(gaps):>9.3f}"
                f" {median(costs):>7.0f}"
                f" {sum(gap <= 1e-4 for gap in gaps)}/{len(SEEDS)}"
            )

    logging.disable(logging.NOTSET)


if __name__ == "__main__":
    main()
