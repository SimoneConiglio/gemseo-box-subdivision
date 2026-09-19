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
"""The methods compared by the benchmarks, behind one interface.

Every method is given the **same budget of objective evaluations** and is stopped
as soon as it is spent, so that the comparison is at equal cost rather than at
equal number of iterations, which means nothing across such different methods.

Because a method using the gradient cannot be compared with one that does not on
the number of objective evaluations alone, the budget is counted in *equivalent*
evaluations, under one of two conventions:

- ``adjoint``, where a gradient costs one evaluation, which is the situation the
  box-subdivision method targets, an adjoint being available;
- ``finite differences``, where a gradient costs as many evaluations as there are
  design variables, which is the situation of a black box.

The methods that do not use the gradient are unaffected by the convention, so
reporting both brackets the comparison instead of picking the flattering one.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING
from typing import Any

from gemseo.algos.design_space import DesignSpace
from gemseo.algos.opt.factory import OptimizationLibraryFactory
from gemseo.algos.optimization_problem import OptimizationProblem
from gemseo.core.mdo_functions.mdo_function import MDOFunction
from gemseo_bilevel_outer_approximation.algos.opt.bilevel_master_outer_approximation.bilevel_master_outer_approximation_settings import (  # noqa: E501
    BiLevelMasterOuterApproximation_Settings,
)
from numpy import array
from numpy import full
from numpy.random import default_rng

from benchmarks.configurations import CONFIGURATIONS
from benchmarks.configurations import DEFAULT_CONFIGURATION
from benchmarks.configurations import TRUST_REGION_RADIUS
from benchmarks.problems import Counter
from benchmarks.problems import Objective
from gemseo_box_subdivision import BoxSubdivisionScenario
from gemseo_box_subdivision import SweptBoxSubdivisionSettings

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy import ndarray

    from benchmarks.problems import Problem

MAX_BOXES = 100
"""The number of boxes the subdivision of the comparison aims at.

The boxes being the Cartesian product of the subdivisions, a fixed number of them
per variable makes their count explode with the dimension, and holding the
*product* roughly constant instead keeps the comparison cheap: it reproduces ten
subdivisions per variable in two dimensions and two in five.

It is a budget, **not** a limit of the method. The master grows with the one-hot
binaries, the sum of the numbers of subdivisions, not with their product: five
variables with ten subdivisions each is a hundred thousand boxes and only fifty
binaries. Provided the trust region is sized to the design space, that density
solves Rastrigin in five dimensions, which nothing in this comparison does, for
about three thousand four hundred evaluations, where this default returns a gap
of five.

What the subdivision has to do is resolve the basins of the landscape, and this
default does not always manage it, which is why it leaves that result on the
table. Refining past the basins is waste rather than danger: Styblinski-Tang and
Griewank, whose basins two subdivisions per variable already separate, only get
more expensive at ten.
"""


def default_n_subdivisions(dimension: int, max_boxes: int = MAX_BOXES) -> int:
    """Return the number of subdivisions keeping the number of boxes bounded.

    Args:
        dimension: The number of design variables.
        max_boxes: The number of boxes aimed at.

    Returns:
        The number of subdivisions per variable, at least two.
    """
    return max(2, int(max_boxes ** (1.0 / dimension)))


METHODS = (
    "box_subdivision",
    "box_subdivision_swept",
    "multistart",
    "cmaes",
    "direct",
    "egobox",
)
"""The methods compared."""


N_DOE_PER_VARIABLE = 5
"""The size of the initial design of experiments of EGO, per design variable."""


class BudgetExceededError(Exception):
    """Raised to stop a method once its budget of evaluations is spent."""


@dataclass(frozen=True)
class Result:
    """The outcome of one run of one method."""

    method: str
    problem: str
    dimension: int
    seed: int
    best: float
    n_objective: int
    n_gradient: int
    cost_adjoint: int
    cost_finite_differences: int
    budget: int = 0

    @property
    def truncated(self) -> bool:
        """Whether the run was stopped by its budget rather than by itself.

        A run that spends its whole budget was still searching when it was cut
        off, so its distance to the optimum is an upper bound on what the same
        configuration would reach with more evaluations. Comparing two truncated
        runs ranks how far each got within the budget, which is a weaker
        statement than ranking how well each solves the problem.
        """
        return bool(self.budget) and self.cost_adjoint >= self.budget

    def gap(self, optimum: float) -> float:
        """Return the distance to the global minimum.

        Args:
            optimum: The global minimum.

        Returns:
            The distance to the global minimum.
        """
        return self.best - optimum


class BudgetedCounter(Counter):
    """A counter that stops a method once its budget is spent."""

    def __init__(
        self, problem: Problem, dimension: int, budget: int, adjoint: bool
    ) -> None:
        """
        Args:
            problem: The problem to count the calls to.
            dimension: The number of design variables.
            budget: The budget in equivalent objective evaluations.
            adjoint: Whether a gradient costs one objective evaluation.
        """  # noqa: D205, D212
        super().__init__(problem)
        self.__dimension = dimension
        self.budget = budget
        self.__adjoint = adjoint

    def __check(self) -> None:
        """Stop the method when the budget is spent.

        Raises:
            BudgetExceededError: When the budget is spent.
        """
        if self.cost(self.__dimension, self.__adjoint) >= self.budget:
            raise BudgetExceededError

    def objective(self, x: ndarray) -> float:  # noqa: D102
        self.__check()
        return super().objective(x)

    def gradient(self, x: ndarray) -> ndarray:  # noqa: D102
        self.__check()
        return super().gradient(x)


def _design_space(problem: Problem, dimension: int, value: ndarray) -> DesignSpace:
    """Return the design space of a problem.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        value: The initial value.

    Returns:
        The design space.
    """
    design_space = DesignSpace()
    design_space.add_variable(
        "x",
        lower_bound=problem.lower_bound,
        upper_bound=problem.upper_bound,
        size=dimension,
        value=value,
    )
    return design_space


def _starting_point(problem: Problem, dimension: int, seed: int) -> ndarray:
    """Return a starting point drawn at random in the bounds.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the draw.

    Returns:
        The starting point.
    """
    return default_rng(seed).uniform(
        problem.lower_bound, problem.upper_bound, dimension
    )


def run_box_subdivision(
    problem: Problem,
    dimension: int,
    seed: int,
    budget: int,
    adjoint: bool,
    n_subdivisions: int = 0,
    configuration: str = DEFAULT_CONFIGURATION,
    overrides: Mapping[str, Any] = MappingProxyType({}),
    weights: ndarray | None = None,
) -> Result:
    """Run the box-subdivision outer approximation.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the starting point.
        budget: The budget in equivalent objective evaluations.
        adjoint: Whether a gradient costs one objective evaluation.
        n_subdivisions: The number of subdivisions per variable.
            If zero, use :func:`.default_n_subdivisions`.
        configuration: The configuration of the master, either
            ``"adaptive"`` or ``"pure_convexification"``. The two are
            different mechanisms and are not combined.
        overrides: The settings of the master to override, to sweep one of them
            without defining a configuration of its own.
        weights: The weights of the subdivisions in the distance the trust
            region of the master measures. If ``None``, use the subdivision
            indexes, which is what the catalogue does on its own.

    The trust region of the master keeps its radius at
    :data:`.TRUST_REGION_RADIUS`, so that an iteration changes a couple of
    components at most, which is what the measurements support.

    Returns:
        The outcome of the run.
    """
    counter = BudgetedCounter(problem, dimension, budget, adjoint)
    design_space = _design_space(
        problem, dimension, _starting_point(problem, dimension, seed)
    )
    scenario = BoxSubdivisionScenario(
        [Objective(counter, dimension)],
        "f",
        design_space,
        n_subdivisions=n_subdivisions or default_n_subdivisions(dimension),
        weights={} if weights is None else dict.fromkeys(["x"], weights),
    )
    settings = dict(CONFIGURATIONS[configuration])
    settings["max_step"] = TRUST_REGION_RADIUS
    settings.update(overrides)

    # A budget spent inside a linearization leaves the discipline without its
    # output, which GEMSEO then reports as a missing key rather than as the
    # budget error raised underneath it.
    with suppress(BudgetExceededError, KeyError):
        scenario.execute(
            BiLevelMasterOuterApproximation_Settings(
                max_iter=10000, ub_tol=1e-4, **settings
            )
        )

    return _result("box_subdivision", problem, dimension, seed, counter, adjoint)


def run_swept_box_subdivision(
    problem: Problem,
    dimension: int,
    seed: int,
    budget: int,
    adjoint: bool,
    n_subdivisions: int = 0,
) -> Result:
    """Run the method with the convexity swept rather than calibrated.

    The same method as :func:`.run_box_subdivision`, asked for through the entry
    point that supplies **no convexity value at all**: the ladder is spread over
    the parallel probes the master already runs, and its upper bound is read off
    the spread of the objective over the boxes already solved.

    This is the configuration a user gets without tuning anything, which is what
    makes it the one to compare against the baselines: every other row of this
    benchmark carries a margin chosen on the problem it is run on.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the starting point.
        budget: The budget in equivalent objective evaluations.
        adjoint: Whether a gradient costs one objective evaluation.
        n_subdivisions: The number of subdivisions per variable.
            If zero, use :func:`.default_n_subdivisions`.

    Returns:
        The outcome of the run.
    """
    counter = BudgetedCounter(problem, dimension, budget, adjoint)
    design_space = _design_space(
        problem, dimension, _starting_point(problem, dimension, seed)
    )
    scenario = BoxSubdivisionScenario(
        [Objective(counter, dimension)],
        "f",
        design_space,
        n_subdivisions=n_subdivisions or default_n_subdivisions(dimension),
        settings=SweptBoxSubdivisionSettings(
            trust_region_radius=TRUST_REGION_RADIUS,
            n_parallel_points=CONFIGURATIONS[DEFAULT_CONFIGURATION][
                "number_of_parallel_points"
            ],
            max_iter=10000,
            tolerance=1e-4,
        ),
    )

    # Executed without arguments, so that the run is the one the settings
    # describe: the master is named and configured by them, and the ladder is
    # driven around its solves where the installed master does not sweep.
    with suppress(BudgetExceededError, KeyError):
        scenario.execute()

    return _result("box_subdivision_swept", problem, dimension, seed, counter, adjoint)


def run_multistart(
    problem: Problem,
    dimension: int,
    seed: int,
    budget: int,
    adjoint: bool,
    n_start: int = 50,
) -> Result:
    """Run the multistart of a local solver, the reference of this problem class.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the design of experiments of the starting points.
        budget: The budget in equivalent objective evaluations.
        adjoint: Whether a gradient costs one objective evaluation.
        n_start: The number of starting points.

    Returns:
        The outcome of the run.
    """
    counter = BudgetedCounter(problem, dimension, budget, adjoint)
    design_space = _design_space(
        problem, dimension, _starting_point(problem, dimension, seed)
    )
    optimization_problem = OptimizationProblem(design_space)
    optimization_problem.objective = MDOFunction(
        counter.objective, "f", jac=counter.gradient
    )
    with suppress(BudgetExceededError):
        OptimizationLibraryFactory().execute(
            optimization_problem,
            algo_name="MultiStart",
            n_start=n_start,
            # MultiStart apportions its own max_iter across the starts, so the
            # settings of the sub-optimization must not carry one.
            opt_algo_settings={},
            doe_algo_settings={"seed": seed},
            max_iter=10000,
        )

    return _result("multistart", problem, dimension, seed, counter, adjoint)


def run_cmaes(
    problem: Problem, dimension: int, seed: int, budget: int, adjoint: bool
) -> Result:
    """Run CMA-ES, which does not use the gradient.

    Its budget is enforced by its own ``maxfevals``, which is exact.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the strategy.
        budget: The budget in objective evaluations.
        adjoint: Unused, CMA-ES using no gradient.

    Returns:
        The outcome of the run.
    """
    import cma

    counter = Counter(problem)
    lower, upper = problem.lower_bound, problem.upper_bound
    with suppress(BudgetExceededError):
        cma.fmin(
            counter.objective,
            _starting_point(problem, dimension, seed),
            (upper - lower) / 4.0,
            options={
                "bounds": [lower, upper],
                "maxfevals": budget,
                "seed": seed,
                "verbose": -9,
                "verb_disp": 0,
                "verb_log": 0,
            },
        )

    return _result("cmaes", problem, dimension, seed, counter, adjoint)


def run_direct(
    problem: Problem, dimension: int, seed: int, budget: int, adjoint: bool
) -> Result:
    """Run DIRECT, which is deterministic and ignores the starting point.

    Its budget is enforced by its own ``maxfun``, which is exact. Raising from
    its objective is not an option, since it is called from a C extension.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: Recorded for the report; DIRECT does not use it.
        budget: The budget in objective evaluations.
        adjoint: Unused, DIRECT using no gradient.

    Returns:
        The outcome of the run.
    """
    from scipy.optimize import direct

    counter = Counter(problem)
    bounds = list(
        zip(
            full(dimension, problem.lower_bound),
            full(dimension, problem.upper_bound),
            strict=True,
        )
    )
    with suppress(BudgetExceededError):
        direct(counter.objective, bounds, maxfun=budget, maxiter=budget)

    return _result("direct", problem, dimension, seed, counter, adjoint)


def run_egobox(
    problem: Problem, dimension: int, seed: int, budget: int, adjoint: bool
) -> Result:
    """Run EGO, the Bayesian optimization of `egobox`.

    This is the baseline of the regime the method targets: a surrogate is fitted
    to every point evaluated so far and the next point is chosen by maximizing an
    expected improvement over it, which is worth its own cost only when an
    evaluation is expensive. It is therefore the one baseline whose comparison at
    equal *evaluations* flatters it least on these analytic problems and most on
    the industrial case the method is built for.

    Its budget is enforced natively and exactly: the number of calls is
    ``n_doe + max_iters``, since the batch size is one. Raising from its objective
    is not an option, the optimizer being a Rust extension.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the initial design of experiments.
        budget: The budget in objective evaluations.
        adjoint: Unused, EGO using no gradient.

    Returns:
        The outcome of the run.
    """
    import egobox as egx  # noqa: PLC0415

    counter = Counter(problem)

    def objective(x: ndarray) -> ndarray:
        """Return the objective at each row, as `egobox` expects it."""
        return array([counter.objective(row) for row in x]).reshape(-1, 1)

    # The usual rule of thumb for the initial design, kept below half the budget
    # so that the surrogate is actually used rather than merely fitted.
    n_doe = max(2, min(N_DOE_PER_VARIABLE * dimension, budget // 2))
    specs = [
        egx.XSpec(egx.XType.FLOAT, [problem.lower_bound, problem.upper_bound])
    ] * dimension
    with suppress(BudgetExceededError):
        egx.Egor(specs, n_doe=n_doe).minimize(
            objective, max_iters=max(1, budget - n_doe), seed=seed
        )

    return _result("egobox", problem, dimension, seed, counter, adjoint)


def _result(
    method: str,
    problem: Problem,
    dimension: int,
    seed: int,
    counter: Counter,
    adjoint: bool,  # noqa: ARG001
) -> Result:
    """Assemble the outcome of a run.

    Args:
        method: The name of the method.
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the run.
        counter: The counter of the calls.
        adjoint: Unused, both conventions being reported.

    Returns:
        The outcome of the run.
    """
    return Result(
        method=method,
        problem=problem.name,
        dimension=dimension,
        seed=seed,
        best=counter.best,
        n_objective=counter.n_objective,
        n_gradient=counter.n_gradient,
        cost_adjoint=counter.cost(dimension, adjoint=True),
        cost_finite_differences=counter.cost(dimension, adjoint=False),
        budget=getattr(counter, "budget", 0),
    )


RUNNERS = {
    "box_subdivision": run_box_subdivision,
    "box_subdivision_swept": run_swept_box_subdivision,
    "multistart": run_multistart,
    "cmaes": run_cmaes,
    "direct": run_direct,
    "egobox": run_egobox,
}
"""The runner of each method."""


def run(
    method: str,
    problem: Problem,
    dimension: int,
    seed: int,
    budget: int,
    adjoint: bool = True,
) -> Result:
    """Run one method on one problem.

    Args:
        method: The name of the method.
        problem: The problem.
        dimension: The number of design variables.
        seed: The seed of the run.
        budget: The budget in equivalent objective evaluations.
        adjoint: Whether a gradient costs one objective evaluation.

    Returns:
        The outcome of the run.
    """
    logging.disable(logging.CRITICAL)
    try:
        return RUNNERS[method](problem, dimension, seed, budget, adjoint)
    finally:
        logging.disable(logging.NOTSET)
