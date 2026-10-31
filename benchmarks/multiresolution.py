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
r"""One master, several levels of subdivision, and far fewer binaries.

The hierarchies of `benchmarks/hierarchy.py` put the levels in *different*
masters, one after the other, and pay for it: each node restarts a master and
discards the cuts of its parent. This puts them in the **same** master instead.

A box is chosen by one categorical variable per level rather than by one over the
whole subdivision. With $L$ levels of $m$ subdivisions each, the lower bound of a
component is the sum of the fractions of the design space its levels select,

$$
l_j(\alpha) = L_j + \Delta_j \sum_{k=1}^{L} m^{-k} \, d_k(\alpha_j),
\qquad
u_j(\alpha) = l_j(\alpha) + \Delta_j m^{-L},
$$

with $\Delta_j = U_j - L_j$ and $d_k \in \{0, \dots, m-1\}$ the subdivision chosen
at level $k$, one-hot encoded. That is the **base-$m$ representation** of the box
index: the levels are its digits.

The consequences are the point of the construction.

- The resolution is $m^L$ per component while the binaries are $n m L$, so a
  resolution of sixteen over five variables costs $40$ binaries against the $80$
  of the flat encoding, and a resolution of $1024$ costs $100$ against $5120$.
- The bounds stay **affine** in the one-hot variables and the width no longer
  depends on them at all, so the mapping $x = l(\alpha) + \xi \Delta m^{-L}$ is
  bilinear in $(\xi, \alpha)$ exactly as the one-level one, with constant
  Jacobian blocks.
- One master holds every level, so nothing is discarded and nothing is
  committed: the master may change a coarse digit and a fine one in the same
  iteration, which is the backtracking the hierarchies lacked.

The price is the **model class**. The cut model is linear in the one-hot
variables, so over the digits it is additive: it can represent what a level
contributes on its own, and not that the effect of a fine digit depends on the
coarse one. A flat encoding has one coefficient per box index and no such
restriction.

```shell
python -m benchmarks.multiresolution
```
"""

from __future__ import annotations

import logging
from contextlib import suppress
from statistics import median
from typing import TYPE_CHECKING

from gemseo import create_scenario
from gemseo.core.discipline import Discipline
from gemseo.discipline import DisciplineChain
from gemseo.formulation import DisciplinaryOpt_Settings
from gemseo.optimization import SLSQP_Settings
from gemseo_bilevel_outer_approximation.algos.design_space.catalogue_design_space import (  # noqa: E501
    CatalogueDesignSpace,
)
from gemseo_bilevel_outer_approximation.algos.opt.bilevel_master_outer_approximation.bilevel_master_outer_approximation_settings import (  # noqa: E501
    BILEVEL_MASTER_OUTER_APPROXIMATION_Settings,
)
from numpy import arange
from numpy import array
from numpy import full
from numpy import minimum
from numpy import ones
from numpy import zeros
from numpy.random import default_rng

from benchmarks.baselines import BudgetedCounter
from benchmarks.baselines import BudgetExceededError
from benchmarks.configurations import CONFIGURATIONS
from benchmarks.configurations import DEFAULT_CONFIGURATION
from benchmarks.configurations import TRUST_REGION_RADIUS
from benchmarks.problems import PROBLEMS

if TYPE_CHECKING:
    from numpy import ndarray

    from benchmarks.problems import Problem

NORMALIZED = "x_normalized"
"""The name of the variable placing a point inside the box."""

DIMENSION = 5
"""The number of design variables."""

BUDGET = 2500
"""The budget in equivalent objective evaluations."""

SEEDS = (11, 101, 202)
"""The seeds of the starting points."""


def level_name(level: int) -> str:
    """Return the name of the one-hot variable of a level.

    The catalogue design space names a categorical variable after its one-hot
    encoding, which is what the master and the mapping both read.

    Args:
        level: The level, from one.

    Returns:
        The name of its one-hot variable.
    """
    return f"x_level_{level}_box"


class MultiResolutionMapping(Discipline):
    r"""The point of a box chosen by one categorical variable per level.

    Maps the normalized position $\xi$ and the digits $\alpha^{(k)}$ to

    $$
    x_j = L_j + \Delta_j \sum_k m^{-k} d_k(\alpha_j) + \xi_j \Delta_j m^{-L},
    $$

    which is affine in each of its inputs, so every Jacobian block is constant.
    """

    def __init__(
        self,
        lower: ndarray,
        upper: ndarray,
        branching: int,
        levels: int,
        counter: BudgetedCounter,
    ) -> None:
        """
        Args:
            lower: The lower bounds of the design space.
            upper: The upper bounds of the design space.
            branching: The number of subdivisions per level.
            levels: The number of levels.
            counter: The counter of the calls to the objective.
        """  # noqa: D205, D212
        super().__init__()
        self.__lower = lower
        self.__width = upper - lower
        self.__branching = branching
        self.__levels = levels
        self.__counter = counter
        self.__dimension = lower.size
        # The value a digit contributes, per level and per catalogue value.
        self.__digits = array([
            branching ** -(level + 1) * arange(branching) for level in range(levels)
        ])
        data = {NORMALIZED: full(self.__dimension, 0.5)}
        for level in range(1, levels + 1):
            data[level_name(level)] = zeros(self.__dimension * branching)

        self.io.input_grammar.update_from_data(data)
        self.io.output_grammar.update_from_data({"f": zeros(1)})
        self.default_input_data = data

    def __position(self, input_data) -> ndarray:  # noqa: ANN001
        """Return the point the inputs select.

        Args:
            input_data: The input data.

        Returns:
            The design value.
        """
        fractions = zeros(self.__dimension)
        for level in range(1, self.__levels + 1):
            one_hot = input_data[level_name(level)].reshape(
                self.__dimension, self.__branching
            )
            fractions += one_hot @ self.__digits[level - 1]

        smallest = self.__branching**-self.__levels
        return (
            self.__lower
            + self.__width * fractions
            + self.__width * smallest * input_data[NORMALIZED]
        )

    def _run(self, input_data):  # noqa: ANN001, ANN202
        return {"f": array([self.__counter.objective(self.__position(input_data))])}

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        gradient = self.__counter.gradient(self.__position(self.io.data))
        smallest = self.__branching**-self.__levels
        self.jac["f"][NORMALIZED] = (gradient * self.__width * smallest).reshape(1, -1)
        for level in range(1, self.__levels + 1):
            # One block per level, of one row and one column per binary.
            block = zeros((1, self.__dimension * self.__branching))
            for component in range(self.__dimension):
                start = component * self.__branching
                block[0, start : start + self.__branching] = (
                    gradient[component]
                    * self.__width[component]
                    * self.__digits[level - 1]
                )

            self.jac["f"][level_name(level)] = block


def digits_of(
    start: ndarray, lower: ndarray, upper: ndarray, branching: int, levels: int
) -> list[list[int]]:
    """Return the digits of the box holding a point, one list per level.

    Args:
        start: The point.
        lower: The lower bounds of the design space.
        upper: The upper bounds of the design space.
        branching: The number of subdivisions per level.
        levels: The number of levels.

    Returns:
        The subdivision chosen at each level, per component.
    """
    fraction = (start - lower) / (upper - lower)
    index = minimum((fraction * branching**levels).astype(int), branching**levels - 1)
    digits = []
    for level in range(1, levels + 1):
        power = branching ** (levels - level)
        digits.append([int(value) for value in (index // power) % branching])

    return digits


def create_design_space(
    lower: ndarray,
    upper: ndarray,
    branching: int,
    levels: int,
    digits: list[list[int]],
    weighting: str = "unit",
) -> CatalogueDesignSpace:
    """Return the design space of a multi-resolution subdivision.

    The weights of a catalogue are what the trust region of the master measures
    distances with. Left to the catalogue values, a digit costs the same at every
    level, although changing the coarsest one moves the box $m^{L-1}$ times
    further than changing the finest. Weighting a level by its **positional
    value** makes the distance proportional to the displacement, which is what a
    trust region is supposed to bound.

    Args:
        lower: The lower bounds of the design space.
        upper: The upper bounds of the design space.
        branching: The number of subdivisions per level.
        levels: The number of levels.
        digits: The subdivision each level starts from, per component.
        weighting: ``"unit"``, the default, to weigh every subdivision of every
            level alike, so that the distance counts the digits a candidate
            changes; ``"positional"`` to weigh a level by what a digit of it is
            worth in the box index; ``"flat"`` to leave the weights at the
            catalogue values, which weighs a digit by its own value.

    Note:
        Positional weights fix the **scale** of a level, and no weighting can
        make this distance a displacement: the master charges the weights the
        *incumbent* holds on the components a candidate changes, never the
        difference between the two, so leaving a digit at zero is free whatever
        the candidate moves to.

    Returns:
        The design space, with one categorical variable per level.
    """
    dimension = lower.size
    design_space = CatalogueDesignSpace()
    design_space.add_variable(
        NORMALIZED,
        lower_bound=zeros(dimension),
        upper_bound=ones(dimension),
        value=full(dimension, 0.5),
        size=dimension,
    )
    for level in range(1, levels + 1):
        weights = None
        if weighting == "unit":
            weights = ones(branching)
        elif weighting == "positional":
            weights = arange(branching) * branching ** (levels - level)

        design_space.add_categorical_variable(
            level_name(level),
            digits[level - 1],
            list(range(branching)),
            weights=weights,
        )

    return design_space


def max_step(
    dimension: int, branching: int, levels: int, weighting: str = "positional"
) -> int:
    """Return the diameter of the design space in the distance of the master.

    Args:
        dimension: The number of design variables.
        branching: The number of subdivisions per level.
        levels: The number of levels.
        weighting: The weighting of the levels, ``"flat"`` or ``"positional"``.

    Returns:
        The largest distance between two boxes.
    """
    if weighting == "unit":
        return dimension * levels

    if weighting == "positional":
        return dimension * (branching**levels - 1)

    return dimension * levels * (branching - 1)


def run(
    problem: Problem,
    dimension: int,
    seed: int,
    budget: int,
    branching: int = 2,
    levels: int = 4,
    weighting: str = "unit",
    configuration: str = DEFAULT_CONFIGURATION,
) -> tuple[float, int]:
    """Run the method with one categorical variable per level.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the starting point.
        budget: The budget in equivalent objective evaluations.
        branching: The number of subdivisions per level.
        levels: The number of levels.
        weighting: The weighting of the levels in the distance of the master,
            ``"flat"`` or ``"positional"``.
        configuration: The configuration of the master.

    Returns:
        The best objective value and the cost under the adjoint convention.
    """
    counter = BudgetedCounter(problem, dimension, budget, adjoint=True)
    lower = full(dimension, problem.lower_bound)
    upper = full(dimension, problem.upper_bound)
    start = default_rng(seed).uniform(
        problem.lower_bound, problem.upper_bound, dimension
    )
    design_space = create_design_space(
        lower,
        upper,
        branching,
        levels,
        digits_of(start, lower, upper, branching, levels),
        weighting,
    )
    settings = dict(CONFIGURATIONS[configuration])
    # The unit metric counts the one-hot groups a candidate changes, and this
    # encoding has one group per level per variable instead of one per variable.
    # A radius of two would let the master change two *digits*, where the flat
    # encoding lets it change two whole variables, so it is scaled by the number
    # of levels to compare like with like. The other weightings have no such
    # equivalence and keep the diameter.
    settings["max_step"] = (
        TRUST_REGION_RADIUS * levels
        if weighting == "unit"
        else max_step(dimension, branching, levels, weighting)
    )
    scenario = create_scenario(
        [
            DisciplineChain([
                MultiResolutionMapping(lower, upper, branching, levels, counter)
            ])
        ],
        "f",
        design_space,
        formulation_name="Benders",
        main_problem_design_variables=[
            level_name(level) for level in range(1, levels + 1)
        ],
        sub_problem_algo_settings=SLSQP_Settings(max_iter=40),
        sub_problem_formulation_settings=DisciplinaryOpt_Settings(),
    )
    with suppress(BudgetExceededError, KeyError):
        scenario.execute(
            BILEVEL_MASTER_OUTER_APPROXIMATION_Settings(
                max_iter=10000, ub_tol=1e-4, **settings
            )
        )

    return counter.best, counter.cost(dimension, adjoint=True)


def main() -> None:
    """Compare the multi-resolution encoding with the flat one."""
    logging.disable(logging.CRITICAL)
    from benchmarks.baselines import run_box_subdivision

    print(
        f"{DIMENSION} variables, budget {BUDGET}, "
        f"median over {len(SEEDS)} starting points\n"
    )
    print(
        f"{'problem':>18} {'encoding':>28} {'binaries':>9} {'resolution':>11}"
        f" {'gap':>9} {'cost':>7} {'reached':>8}"
    )
    for name in ("rastrigin", "ackley", "styblinski_tang"):
        problem = PROBLEMS[name]
        optimum = problem.optimum(DIMENSION)
        for subdivisions in (10, 16):
            outcomes = [
                run_box_subdivision(
                    problem,
                    DIMENSION,
                    seed,
                    BUDGET,
                    adjoint=True,
                    n_subdivisions=subdivisions,
                )
                for seed in SEEDS
            ]
            _report(
                name,
                f"flat, m={subdivisions}",
                DIMENSION * subdivisions,
                subdivisions,
                [outcome.gap(optimum) for outcome in outcomes],
                [outcome.cost_adjoint for outcome in outcomes],
            )

        for branching, levels, weighting in (
            (2, 4, "unit"),
            (2, 5, "unit"),
            (4, 2, "unit"),
            (4, 3, "unit"),
            (2, 4, "positional"),
        ):
            outcomes = [
                run(problem, DIMENSION, seed, BUDGET, branching, levels, weighting)
                for seed in SEEDS
            ]
            _report(
                name,
                f"levels m={branching}, L={levels}, {weighting}",
                DIMENSION * branching * levels,
                branching**levels,
                [best - optimum for best, _ in outcomes],
                [cost for _, cost in outcomes],
            )

    logging.disable(logging.NOTSET)


def _report(
    problem: str,
    encoding: str,
    binaries: int,
    resolution: int,
    gaps: list[float],
    costs: list[int],
) -> None:
    """Print one row of the comparison.

    Args:
        problem: The name of the problem.
        encoding: The name of the encoding.
        binaries: The number of binaries of the master.
        resolution: The number of subdivisions per variable reached.
        gaps: The distances to the optimum.
        costs: The costs.
    """
    print(
        f"{problem:>18} {encoding:>28} {binaries:>9} {resolution:>11}"
        f" {median(gaps):>9.3f} {median(costs):>7.0f}"
        f" {sum(gap <= 1e-4 for gap in gaps)}/{len(gaps)}"
    )


if __name__ == "__main__":
    main()
