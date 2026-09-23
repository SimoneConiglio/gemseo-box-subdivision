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
r"""Estimate the density of the subdivision, instead of supplying it.

The number of subdivisions is the setting this method cannot default: it has to
follow the **spacing of the basins**, which is a property of the landscape and
not of the dimension. Ten per variable is the best density of this benchmark for
three problems and the worst for the fourth.

What that setting needs is not a wavelength. For a general objective there is no
single wavelength per direction: the restriction of :math:`f` to a line along
:math:`e_j` has a spectrum that depends on where the line is. The quantity that
is well defined for any :math:`C^1` objective is the expected number of minima
along such a line,

.. math::

    N_j = \mathbb{E}_{x_\perp}
          \big[\#\{t : \partial_j f(x_\perp + t e_j) = 0,\
                       \partial_{jj} f(x_\perp + t e_j) > 0\}\big],

which is what the subdivision has to separate, so :math:`m_j = N_j` directly.
That expectation is a Monte Carlo integral, and this module estimates it by
**axial line scans**: draw an anchor at random, sweep one component across its
bounds, count the minima deep enough to matter.

Three properties of the estimator are not details.

**A space-filling design cannot replace the scans.** Averaging a Latin hypercube
over the other components estimates the ANOVA main effect
:math:`\mathbb{E}[f \mid x_j]`, and multimodality carried by the interactions
does not survive that average. Griewank's ripples are a product over every
component and Ackley's are inside a norm, so a main effect reports neither.

**The count has to be gated by amplitude, not only by frequency.** A component
the objective barely varies in deserves one subdivision whatever its roughness,
which is what :data:`.DEPTH_RATIO` enforces, and it is what makes an estimate
select the variables to subdivide at all rather than only their density.

**The scan has to be irregular.** A uniform scan whose spacing resonates with
the landscape aliases, and aliasing is silent: on Ackley a uniform ladder
reports one basin at two consecutive rates before jumping to sixty-two at the
third, so the rule "stop when the count stops growing" terminates at the wrong
answer having agreed with itself twice. Drawing the abscissae at random removes
the resonance, and a ladder that has not resolved the landscape then fails to
converge rather than converging on a lie. :func:`.estimate_basins` reports that
as :attr:`.BasinEstimate.converged`, and the comparison is printed by this
benchmark.

The estimate implies a **budget** as well as a density. The cut model carries
:math:`\sum_j m_j` coefficients, one per one-hot coordinate, and a coordinate no
cut has yet distinguished is ranked by extrapolation, so the master needs of the
order of :math:`\sum_j m_j` sub-problems before its ranking is informed
everywhere. That is a lower bound on the sub-problems to buy, linear in the
binaries; it is not an upper bound on the density. Nothing in the method grows
with the number of boxes, and nothing caps the binaries.

```shell
python -m benchmarks.basin_spacing
```
"""

from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass
from statistics import median
from typing import TYPE_CHECKING
from typing import Final

from gemseo import create_scenario
from gemseo.algos.design_space import DesignSpace
from gemseo.core.chains.chain import MDOChain
from gemseo.core.discipline import Discipline
from gemseo.settings.formulations import DisciplinaryOpt_Settings
from gemseo.settings.opt import SLSQP_Settings
from gemseo_bilevel_outer_approximation.algos.opt.bilevel_master_outer_approximation.bilevel_master_outer_approximation_settings import (  # noqa: E501
    BiLevelMasterOuterApproximation_Settings,
)
from numpy import argmax
from numpy import array
from numpy import atleast_2d
from numpy import diff
from numpy import empty
from numpy import sort
from numpy import tile
from numpy import where
from numpy import zeros
from numpy.random import default_rng

from benchmarks.baselines import BudgetedCounter
from benchmarks.baselines import BudgetExceededError
from benchmarks.configurations import CONFIGURATIONS
from benchmarks.configurations import DEFAULT_CONFIGURATION
from benchmarks.configurations import TRUST_REGION_RADIUS
from benchmarks.problems import PROBLEMS

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Sequence

    from numpy import ndarray

    from benchmarks.problems import Problem

from gemseo_box_subdivision.design_spaces import create_normalized_box_design_space
from gemseo_box_subdivision.disciplines.box_mapping import BoxMapping
from gemseo_box_subdivision.subdivisions.box import BoxSubdivision

DIMENSION: Final[int] = 5
"""The number of design variables."""

N_LINES: Final[int] = 5
"""The number of anchors averaged per component.

The estimate is a Monte Carlo mean over :math:`x_\\perp`, and the median over a
handful of anchors is enough because what varies between lines is which basins
are visible, not how many there are.
"""

DEPTH_RATIO: Final[float] = 0.02
"""The depth below which a minimum is not counted, as a fraction of the range.

This is the amplitude gate. A dip shallower than this is not a basin worth a box
of its own, and a component carrying none of them is reported as needing a single
subdivision however fast the objective wiggles in it.
"""

LADDER: Final[tuple[int, ...]] = (17, 33, 65, 129, 257, 513)
"""The numbers of points per scan, each rung about twice the one before.

Counting a minimum needs two samples per basin while boxing it needs one box per
basin, so the scan samples at about twice the density it ends up proposing.
"""

GROWTH_TOLERANCE: Final[float] = 0.1
"""The relative growth below which a rung of the ladder counts as converged.

The error of the estimator is one sided: a scan reveals only the basins it
resolves, never more, so a count that is still climbing means the ladder has not
finished and not that the landscape is rough in a way already measured.
"""

COST_PER_SUB_PROBLEM: Final[int] = 40
"""The evaluations one sub-problem costs, used to turn a density into a budget.

The enumeration of `benchmark.md` solves a hundred boxes of Rastrigin in two
dimensions for about fourteen hundred executions, some fourteen each; a local
solve over five variables costs more, and this is the order of it. It converts
:math:`\\sum_j m_j` sub-problems into evaluations and nothing else depends on it.
"""

DEFAULT_STALL: Final[int] = 10
"""The stalling iterations the master allows before giving up.

This is ``upper_bound_stall`` as the catalogue defaults it, and it is the floor
of :func:`.stall_counter`. On its own it decides nothing: raised to the binaries
while the trust region still collapses, it leaves an Ackley run at ten
subdivisions bit for bit where it was, the same gap for the same evaluations.
It matters only once the region is held open, see :data:`.MIN_STEP`.
"""

MIN_STEP: Final[int] = TRUST_REGION_RADIUS
"""The radius the trust region of the master may not shrink below.

The master shrinks its step by $0.7$ every ``step_decreasing_activation``
stalling iterations, down to ``min_step``, and widens it again only on an
improvement. The catalogue floor is one, so six stalling iterations pin the
region at a radius of one for good, and the run then changes a single component
at a time for as long as it is allowed to.

That also silences the parallel probes. The master gives one radius per point
over ``geomspace(max(step / 2, min_step), step)``, so four points at a step of
two probe $1$, $1.26$, $1.59$ and $2$; once the step reaches one they all probe
$1$, and the four parallel points solve the same problem four times.

Holding the floor at the tuned radius keeps that from happening: Ackley at ten
subdivisions goes from $6.30$ to $4.95$ and Styblinski-Tang from two starting
points out of three to three, both for a few percent more evaluations.

It cannot be done alone. A region that stays wide stalls more often than one
that narrows onto whatever it can still improve, so holding it open and leaving
the patience at ten stops the run earlier in the search rather than later:
Rastrigin, solved from every starting point at $2103$ evaluations, falls to
$0.99$ and one starting point out of three. With :func:`.stall_counter` sizing
the patience as well it is solved again, from every starting point. The two
settings are one change.
"""

HEADROOM: Final[int] = 4
"""How many times the predicted budget a run is actually granted.

The prediction to test is that a density needs of the order of :math:`\\sum_j
m_j` sub-problems, and a run stopped at exactly that many would test the
arithmetic of :data:`.COST_PER_SUB_PROBLEM` instead. Granting several times the
prediction lets every run end on its own criterion, so the cost it reports is
what the density *wanted* rather than what it was allowed, and the prediction is
read by comparing the two.
"""

SEEDS: Final[tuple[int, ...]] = (11, 101, 202)
"""The seeds of the starting points."""


@dataclass(frozen=True)
class BasinEstimate:
    """The density proposed for a problem, and what supports it."""

    n_subdivisions: tuple[int, ...]
    """The number of basins found along each component, which is the density."""

    converged: bool
    """Whether the ladder stopped growing before it ran out of rungs.

    When this is false the estimate is a **lower bound** that the scans never
    settled on, and the density it proposes is the coarsest the landscape
    permits rather than the one it needs.
    """

    ladder: tuple[tuple[int, ...], ...]
    """The counts at each rung of the ladder, coarsest first."""

    n_points: int
    """The number of points per scan of the rung the estimate stopped on."""

    cost: int
    """The objective evaluations the estimate spent."""

    @property
    def n_binaries(self) -> int:
        """The coefficients of the cut model the proposed density implies."""
        return sum(self.n_subdivisions)

    @property
    def budget(self) -> int:
        """The evaluations the proposed density implies buying."""
        return self.n_binaries * COST_PER_SUB_PROBLEM


def count_minima(values: ndarray, depth_ratio: float = DEPTH_RATIO) -> int:
    """Count the local minima of a scan that are deep enough to be basins.

    A minimum is kept when the rise bounding it exceeds ``depth_ratio`` of the
    range of the scan. That prominence is what separates a basin from the
    numerical texture of a slope, and it is what gates a component the objective
    is flat in.

    The rise is the smaller of the two bounding it, except where one of them
    lies **outside the bounds**. The objective descends into the design space
    from an edge whenever the ridge that would close the outermost basin is
    beyond it, and charging that basin for a ridge the design space does not
    contain drops it: on Rastrigin the minimum nearest the lower bound sits a
    tenth of a unit inside it, and its prominence measured against both sides
    straddles the gate from one anchor to the next. A basin the bounds clip is
    still a basin the subdivision has to separate, so it is measured against the
    side that exists, which is what keeps the count at the ten that aligns the
    boxes with the lattice.

    Args:
        values: The objective values along the scan.
        depth_ratio: The prominence below which a minimum is not counted, as a
            fraction of the range of the scan.

    Returns:
        The number of basins seen, at least one.
    """
    span = float(values.max() - values.min())
    if span <= 0.0:
        return 1

    slopes = diff(values)
    last = values.size - 1
    kept = 0
    for index in where((slopes[:-1] < 0.0) & (slopes[1:] > 0.0))[0] + 1:
        left = values[: index + 1]
        right = values[index:]
        rises = []
        # A rise peaking on an endpoint of the scan is the objective still
        # climbing when the design space stops, not a ridge closing the basin.
        if int(argmax(left)) != 0:
            rises.append(float(left.max()))
        if int(argmax(right)) + index != last:
            rises.append(float(right.max()))

        # Both sides clipped: the whole scan descends into one basin.
        prominence = min(rises) if rises else max(float(left[0]), float(right[-1]))
        if (prominence - float(values[index])) / span > depth_ratio:
            kept += 1

    return max(kept, 1)


def scan_axis(
    objective: Callable[[ndarray], ndarray],
    lower_bound: float,
    upper_bound: float,
    dimension: int,
    axis: int,
    n_points: int,
    rng,  # noqa: ANN001
    n_lines: int = N_LINES,
    depth_ratio: float = DEPTH_RATIO,
    jitter: bool = True,
) -> float:
    """Count the basins along one component, from anchors drawn at random.

    Args:
        objective: The objective, evaluated over a matrix of points.
        lower_bound: The lower bound of every component.
        upper_bound: The upper bound of every component.
        dimension: The number of design variables.
        axis: The component to scan.
        n_points: The number of points of each scan.
        rng: The generator of the anchors and of the abscissae.
        n_lines: The number of anchors to average over.
        depth_ratio: The prominence gate of :func:`.count_minima`.
        jitter: Whether to draw the abscissae at random rather than to space
            them evenly. Even spacing aliases silently against a periodic
            landscape, which is what this benchmark measures.

    Returns:
        The median number of basins over the anchors.
    """
    span = upper_bound - lower_bound
    counts = []
    for _ in range(n_lines):
        if jitter:
            abscissae = sort(lower_bound + rng.random(n_points) * span)
        else:
            abscissae = array([
                lower_bound + span * index / (n_points - 1) for index in range(n_points)
            ])

        points = tile(lower_bound + rng.random(dimension) * span, (n_points, 1))
        points[:, axis] = abscissae
        counts.append(count_minima(objective(points), depth_ratio))

    return median(counts)


def estimate_basins(
    objective: Callable[[ndarray], ndarray],
    lower_bound: float,
    upper_bound: float,
    dimension: int = DIMENSION,
    seed: int = 0,
    n_lines: int = N_LINES,
    depth_ratio: float = DEPTH_RATIO,
    ladder: Sequence[int] = LADDER,
    growth_tolerance: float = GROWTH_TOLERANCE,
    jitter: bool = True,
) -> BasinEstimate:
    """Propose a number of subdivisions per component, by refining a ladder.

    The scans are repeated at rates about twice the one before until the counts
    stop growing, which is the only stopping rule available: no finite sample
    can bound the roughness of an objective from below, so the ladder can
    certify that a landscape has at least this many basins and never that it has
    no more.

    Args:
        objective: The objective, evaluated over a matrix of points.
        lower_bound: The lower bound of every component.
        upper_bound: The upper bound of every component.
        dimension: The number of design variables.
        seed: The seed of the anchors and of the abscissae.
        n_lines: The number of anchors to average over, per component.
        depth_ratio: The prominence gate of :func:`.count_minima`.
        ladder: The numbers of points per scan to try, coarsest first.
        growth_tolerance: The relative growth below which the ladder stops.
        jitter: Whether to draw the abscissae at random.

    Returns:
        The proposed density, and whether the ladder converged on it.
    """
    rungs: list[tuple[int, ...]] = []
    cost = 0
    previous: tuple[int, ...] | None = None
    for n_points in ladder:
        rng = default_rng(seed)
        counts = tuple(
            int(
                scan_axis(
                    objective,
                    lower_bound,
                    upper_bound,
                    dimension,
                    axis,
                    n_points,
                    rng,
                    n_lines,
                    depth_ratio,
                    jitter,
                )
            )
            for axis in range(dimension)
        )
        rungs.append(counts)
        cost += dimension * n_lines * n_points
        if previous is not None and sum(counts) <= sum(previous) * (
            1.0 + growth_tolerance
        ):
            return BasinEstimate(counts, True, tuple(rungs), n_points, cost)

        previous = counts

    return BasinEstimate(rungs[-1], False, tuple(rungs), ladder[-1], cost)


FREE_GROUP: Final[str] = "x_free"
"""The name of the components the estimate leaves unsubdivided."""


def group_by_density(n_subdivisions: Sequence[int]) -> dict[str, tuple[int, ...]]:
    """Group the components sharing a number of subdivisions.

    A subdivision holds one number of subdivisions per *variable*, its bounds
    being a matrix over the components of that variable, so components needing
    different densities have to be different variables. Grouping them by their
    estimate is what lets one run carry a density per component, and it is what
    makes a component estimated at a single basin an ordinary variable of the
    sub-problem rather than a variable subdivided once.

    Args:
        n_subdivisions: The number of subdivisions of each component.

    Returns:
        The components of each variable, by variable name.
    """
    groups: dict[str, list[int]] = {}
    for component, density in enumerate(n_subdivisions):
        name = FREE_GROUP if density <= 1 else f"x_m{density}"
        groups.setdefault(name, []).append(component)

    return {name: tuple(components) for name, components in groups.items()}


class GroupedObjective(Discipline):
    """The objective of a problem whose components are grouped by density."""

    def __init__(
        self,
        counter: BudgetedCounter,
        groups: dict[str, tuple[int, ...]],
        dimension: int,
    ) -> None:
        """
        Args:
            counter: The counter of the calls.
            groups: The components of each variable, by variable name.
            dimension: The number of design variables.
        """  # noqa: D205, D212
        super().__init__()
        self._counter = counter
        self.__groups = groups
        self.__dimension = dimension
        data = {name: zeros(len(components)) for name, components in groups.items()}
        self.io.input_grammar.update_from_data(data)
        self.io.output_grammar.update_from_data({"f": zeros(1)})
        self.default_input_data = data

    def __assemble(self, data) -> ndarray:  # noqa: ANN001
        """Return the design value the groups describe.

        Args:
            data: The input data holding one array per group.

        Returns:
            The design value, in the order of the components.
        """
        x = empty(self.__dimension)
        for name, components in self.__groups.items():
            x[list(components)] = data[name]

        return x

    def _run(self, input_data):  # noqa: ANN001, ANN202
        return {"f": array([self._counter.objective(self.__assemble(input_data))])}

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        gradient = self._counter.gradient(self.__assemble(self.io.data))
        for name, components in self.__groups.items():
            self.jac["f"][name] = atleast_2d(gradient[list(components)])


def stall_counter(n_subdivisions: Sequence[int]) -> int:
    r"""Return the stalling iterations to allow at a density.

    The master gives up after ``upper_bound_stall`` iterations that fail to
    improve the upper bound, and the catalogue default is ten. Ten is a count of
    mistakes tolerated rather than a property of a problem, and two things make
    a run need more of them: a finer subdivision proposes more boxes while the
    ones holding the optimum stay as few, and a trust region held open at
    :data:`.MIN_STEP` keeps proposing from a neighbourhood it has not exhausted
    instead of narrowing onto whatever it can still improve.

    The size follows the coefficients of the cut model, as the budget does. A
    model of :math:`\sum_j m_j` coefficients needs of the order of
    :math:`\sum_j m_j` cuts before its ranking is informed everywhere, so
    giving up after ten non-improving iterations at fifty binaries gives up
    before the model means anything. The catalogue default stays the floor.

    Args:
        n_subdivisions: The number of subdivisions of each component.

    Returns:
        The number of stalling iterations to allow.
    """
    return max(DEFAULT_STALL, sum(n_subdivisions))


def run_at_density(
    problem: Problem,
    dimension: int,
    n_subdivisions: Sequence[int],
    seed: int,
    budget: int,
    stall: int = 0,
    min_step: int = 1,
) -> tuple[float, int, bool]:
    """Run the method with one number of subdivisions per component.

    Args:
        problem: The problem.
        dimension: The number of design variables.
        n_subdivisions: The number of subdivisions of each component.
        seed: The seed of the starting point.
        budget: The budget in equivalent objective evaluations.
        stall: The stalling iterations to allow before giving up.
            If zero, use the catalogue default of :data:`.DEFAULT_STALL`.
        min_step: The radius the trust region may not shrink below.
            The catalogue value of one is the default here, so that this
            comparison varies the density and nothing else; see
            :data:`.MIN_STEP` for what holding it open is worth.

    Returns:
        The best objective value, the cost under the adjoint convention, and
        whether the budget stopped the run rather than the run stopping itself.
    """
    counter = BudgetedCounter(problem, dimension, budget, adjoint=True)
    start = default_rng(seed).uniform(
        problem.lower_bound, problem.upper_bound, dimension
    )
    groups = group_by_density(n_subdivisions)
    design_space = DesignSpace()
    for name, components in groups.items():
        design_space.add_variable(
            name,
            lower_bound=problem.lower_bound,
            upper_bound=problem.upper_bound,
            size=len(components),
            value=start[list(components)],
        )

    subdivided = {
        name: max(n_subdivisions[component] for component in components)
        for name, components in groups.items()
        if name != FREE_GROUP
    }
    subdivision = BoxSubdivision.from_design_space(
        design_space, subdivided, list(subdivided)
    )
    scenario = create_scenario(
        [
            MDOChain([
                BoxMapping(subdivision),
                GroupedObjective(counter, groups, dimension),
            ])
        ],
        "f",
        create_normalized_box_design_space(subdivision, design_space),
        formulation_name="Benders",
        main_problem_design_variables=[f"{name}_box" for name in subdivided],
        sub_problem_algo_settings=SLSQP_Settings(max_iter=40),
        sub_problem_formulation_settings=DisciplinaryOpt_Settings(),
    )
    settings = dict(CONFIGURATIONS[DEFAULT_CONFIGURATION])
    settings["max_step"] = TRUST_REGION_RADIUS
    settings["upper_bound_stall"] = stall or DEFAULT_STALL
    settings["min_step"] = min_step

    # A budget spent inside a linearization leaves the discipline without its
    # output, which GEMSEO then reports as a missing key.
    with suppress(BudgetExceededError, KeyError):
        scenario.execute(
            BiLevelMasterOuterApproximation_Settings(
                max_iter=10000, ub_tol=1e-4, **settings
            )
        )

    cost = counter.cost(dimension, adjoint=True)
    return counter.best, cost, cost >= budget


def _estimate_problem(problem: Problem, jitter: bool = True) -> BasinEstimate:
    """Estimate the density a benchmark problem needs.

    Args:
        problem: The problem.
        jitter: Whether to draw the abscissae at random.

    Returns:
        The proposed density.
    """
    return estimate_basins(
        lambda points: array([problem.objective(point) for point in points]),
        problem.lower_bound,
        problem.upper_bound,
        jitter=jitter,
    )


def _report_estimates() -> dict[str, BasinEstimate]:
    """Print the density proposed for every problem, and return the estimates.

    Returns:
        The estimate of each problem, by name.
    """
    print(
        f"The density proposed by the scans, {DIMENSION} variables, "
        f"{N_LINES} anchors per component\n"
    )
    print(
        f"{'problem':>18} {'proposed m':>18} {'sum':>5} {'budget':>8}"
        f" {'scan cost':>10} {'converged':>10}"
    )
    estimates = {}
    for name, problem in PROBLEMS.items():
        estimate = _estimate_problem(problem)
        estimates[name] = estimate
        density = " ".join(f"{value:3d}" for value in estimate.n_subdivisions)
        print(
            f"{name:>18} {density:>18} {estimate.n_binaries:5d}"
            f" {estimate.budget:8d} {estimate.cost:10d}"
            f" {'yes' if estimate.converged else 'NO':>10}"
        )

    return estimates


def _report_aliasing() -> None:
    """Print the ladder of Ackley with and without jitter.

    The uniform ladder is the failure the jitter exists to prevent: it settles
    on a count two rungs running before finding the landscape, so a stopping
    rule reading it terminates on an answer that is wrong by a factor of sixty.
    """
    print("\nWhy the scan is irregular: the ladder of Ackley, by rung\n")
    problem = PROBLEMS["ackley"]
    print(f"{'scan':>10} {'rung':>28} {'stopped on':>12}")
    for jitter in (False, True):
        estimate = _estimate_problem(problem, jitter=jitter)
        rungs = " ".join(f"{sum(rung) // DIMENSION:4d}" for rung in estimate.ladder)
        stopped = (
            f"{sum(estimate.n_subdivisions) // DIMENSION}"
            if estimate.converged
            else "did not"
        )
        print(f"{'jittered' if jitter else 'uniform':>10} {rungs:>28} {stopped:>12}")


FIXED_DENSITIES: Final[tuple[int, ...]] = (2, 10)
"""The densities to compare the estimate against.

Two is what `baselines.py` defaults to at five variables, holding the number of
boxes near a hundred; ten is the best density this benchmark found, and the
worst of the four on Styblinski-Tang. Neither is a rule, which is what an
estimate would replace.
"""


def _report_densities(estimates: dict[str, BasinEstimate]) -> None:
    """Run every problem at the proposed density, against the fixed ones.

    Each problem is given the budget its own estimate implies, so a density that
    needs more sub-problems is allowed to buy them. What that budget cannot buy
    is iterations the master declines to take: a run ending below its budget
    stopped on its own trust region or stall counter, and more evaluations do
    not reach it.

    Args:
        estimates: The estimate of each problem, by name.
    """
    print(
        f"\nThe proposed density against the fixed ones, {DIMENSION} variables, "
        f"median over {len(SEEDS)} starting points,\n"
        f"every run granted {HEADROOM} times the budget its own estimate "
        f"predicts, so that it ends on its own criterion\n"
    )
    print(
        f"{'problem':>18} {'density':>18} {'binaries':>9} {'predicted':>10}"
        f" {'gap':>10} {'cost':>7} {'reached':>8}"
    )
    for name, problem in PROBLEMS.items():
        estimate = estimates[name]
        budget = estimate.budget * HEADROOM
        optimum = problem.optimum(DIMENSION)
        # A fixed density the estimate happens to propose is the same run twice.
        densities = dict.fromkeys([
            tuple(estimate.n_subdivisions),
            *((fixed,) * DIMENSION for fixed in FIXED_DENSITIES),
        ])
        for density in densities:
            # At the catalogue settings, so that what this table varies is the
            # density. Holding the trust region open changes every row of it
            # and is measured on its own, in annex D.
            outcomes = [
                run_at_density(problem, DIMENSION, density, seed, budget)
                for seed in SEEDS
            ]
            gaps = [best - optimum for best, _, _ in outcomes]
            predicted = sum(density) * COST_PER_SUB_PROBLEM
            print(
                f"{name:>18} {' '.join(f'{v:3d}' for v in density):>18}"
                f" {sum(density):9d} {predicted:10d} {median(gaps):10.4f}"
                f" {median([cost for _, cost, _ in outcomes]):7.0f}"
                f" {sum(gap < 1e-2 for gap in gaps):5d}/{len(SEEDS)}"
            )


def main() -> None:
    """Estimate the density of every problem, then test what it predicts."""
    logging.disable(logging.CRITICAL)
    estimates = _report_estimates()
    _report_aliasing()
    _report_densities(estimates)


if __name__ == "__main__":
    main()
