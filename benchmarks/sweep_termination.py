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
r"""Why a swept run stops, read off the master without changing what it does.

Annex D reports that the swept runs of Rastrigin in five variables at ten
subdivisions stop after about $1547$ evaluations one basin away from the optimum,
and leaves the reason open. This module records what the master does at every
mixed-integer solve, and says which of its criteria ended the run.

The recording wraps :meth:`.OuterApproximationOptimizer._solve_milp` *beneath*
the sweep driver, which captures whatever is installed when its context opens,
so every rung a probe climbs through is seen, and it changes no argument and no
result: the runs reproduce the published costs to the evaluation.

What it shows on that row is the following.

- Every run ends on the **lower-bound test** of the outer approximation,
  :math:`\eta^* > \mathrm{UBD} + \mathtt{ub\_tol}`, with the stall counter at one
  to three out of ten, a fifth of the budget spent, and every probe of the last
  iteration still proposing a new box: neither the stall counter, the budget nor
  the exhaustion of the ladder is what stops it.
- At that point the incumbent is one component away from the box holding the
  optimum, inside the trust region and never solved, and **every rung** predicts
  that box above the incumbent.
- The low rungs do so because the raw cuts of a non-convex objective
  over-predict. The high rungs do so because the least-squares repair does not
  lower the prediction at a box nobody has solved: the margin reaches such a box
  through the minimum-norm solution, with a sign set by the geometry of the boxes
  solved, and :func:`margin_sensitivity` measures it at $+0.31$ to $+0.85$ per
  unit of margin for some cuts. The top rung, ten times the spread, then *closes*
  the box it was meant to open.

The convexification constant has no such sign: its correction of a cut at a box
is minus the constant times the number of components the box changes, so a
higher rung lowers every unexplored box, the farther the more, which is what the
ladder assumes; see :func:`convexification_sensitivity`.

**The correction this calls for is upstream**, in the repair itself, and it is
one constraint: solve for the multipliers of the repair under $\mu_i \ge 0$.
The correction of cut $i$ at a box $\alpha$ is then
$-\sum_j \mu_{ij}\,(\alpha-\alpha_i)^\top(\alpha_j-\alpha_i)$, and for one-hot
encodings $(\alpha-\alpha_i)^\top(\alpha_j-\alpha_i) = h(\alpha, \alpha_i) +
h(\alpha_i, \alpha_j) - h(\alpha, \alpha_j) \ge 0$, with $h$ the number of
components two boxes differ in, by the triangle inequality. The repair then
lowers or leaves every prediction at every box, solved or not, and can no longer
close a box. It is what the repair is for anyway: the right-hand side it fits is
clipped at zero, an amount to *lower* each cut by, and only the minimum-norm
solution turned some of it into raising. :func:`nonnegative_repair` installs it
for the length of a measurement, without touching the installed master.

```shell
python -m benchmarks.sweep_termination            # why the runs stop
python -m benchmarks.sweep_termination measure    # Table D.12 with the fix
```
"""

from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from contextlib import nullcontext
from dataclasses import dataclass
from dataclasses import field
from statistics import median
from typing import TYPE_CHECKING
from typing import Any

from gemseo_bilevel_outer_approximation.algos.opt.core import (
    outer_approximation_optimizer as core,
)
from numpy import array
from numpy import atleast_2d
from numpy import isfinite
from numpy import ravel
from numpy import zeros
from numpy.linalg import pinv
from scipy.optimize import nnls

from benchmarks.basin_spacing import COST_PER_SUB_PROBLEM
from benchmarks.basin_spacing import HEADROOM
from benchmarks.basin_spacing import SEEDS
from benchmarks.basin_spacing import run_at_density
from benchmarks.basin_spacing import run_at_density_swept
from benchmarks.problems import PROBLEMS
from gemseo_box_subdivision._convexity_sweep_driver import _probe

if TYPE_CHECKING:
    from collections.abc import Generator
    from collections.abc import Sequence

    from numpy import ndarray

TERMINATIONS = {
    "eta* (": "lower bound",
    "stopped changing": "stall counter",
    "Infeasible MILP": "infeasible master",
    "Maximum iteration reached": "iterations",
}
"""What the master logs when it stops, and what to call it."""


@dataclass
class Solve:
    """One mixed-integer solve of the master."""

    step: float
    """The radius of the trust region of the master."""

    radius: float
    """The radius the probe was given."""

    probe: int
    """The probe, recovered from its radius as the driver does."""

    convexity: float
    """The margin, or the constant, the solve was made at."""

    box: tuple[int, ...]
    """The box proposed, as one index per component."""

    eta: float
    """The optimum of the master."""

    repeated: bool
    """Whether the box proposed has already been solved."""

    upper_bound: float
    """The best value observed so far."""


@dataclass
class Record:
    """What a run of the master did, solve by solve."""

    n_subdivisions: int
    """The subdivisions per component, to read a box off its one-hot encoding."""

    iterations: list[list[Solve]] = field(default_factory=list)
    """The solves, grouped by iteration of the master."""

    messages: list[str] = field(default_factory=list)
    """What the master logged about its stopping criteria."""

    last_call: tuple[Any, tuple[Any, ...], dict[str, Any]] | None = None
    """The master and the arguments of the first solve of the last iteration."""

    @property
    def termination(self) -> str:
        """The criterion that stopped the run, or what is left when none did."""
        for message in reversed(self.messages):
            for key, name in TERMINATIONS.items():
                if key in message:
                    return name

        return "no new candidate, or the budget"


class _Listener(logging.Handler):
    """Keep the messages of the master that open an iteration or stop it."""

    def __init__(self, record: Record) -> None:
        """
        Args:
            record: Where to keep them.
        """  # noqa: D205, D212
        super().__init__(logging.INFO)
        self.__record = record

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        message = record.getMessage()
        if message.startswith("iteration "):
            self.__record.iterations.append([])
            self.__record.last_call = None
        elif any(key in message for key in TERMINATIONS):
            self.__record.messages.append(message)


def _box(alpha: ndarray, n_subdivisions: int) -> tuple[int, ...]:
    """Return the index of the subdivision each component selects.

    Args:
        alpha: The one-hot encoding.
        n_subdivisions: The subdivisions per component.

    Returns:
        The indices.
    """
    return tuple(
        int(i) for i in atleast_2d(alpha).reshape(-1, n_subdivisions).argmax(1)
    )


@contextmanager
def recording(n_subdivisions: int) -> Generator[Record, None, None]:
    """Record every solve of the master, changing nothing it does.

    Open it *outside* the sweep driver, so that the driver wraps the recording
    and every rung it climbs through is recorded.

    Args:
        n_subdivisions: The subdivisions per component.

    Yields:
        The record, filled as the run goes.
    """
    record = Record(n_subdivisions)
    original = core.OuterApproximationOptimizer._solve_milp

    def recorded(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        """Solve, then note what the solve did."""
        if not record.iterations:
            record.iterations.append([])
        if record.last_call is None:
            record.last_call = (self, args, dict(kwargs))
        alpha, eta, feasible = result = original(self, *args, **kwargs)
        radius = kwargs.get("current_step", args[14] if len(args) > 14 else None)
        record.iterations[-1].append(
            Solve(
                step=float(self.current_step),
                radius=float(radius),
                probe=_probe(self, radius),
                convexity=float(
                    self.min_dfk
                    if self.use_adaptative_convexification
                    else self.convexification_constant
                ),
                box=_box(alpha, n_subdivisions),
                eta=float(ravel(eta)[0])
                if feasible and isfinite(eta).all()
                else float("inf"),
                repeated=bool(self._is_previously_computed(atleast_2d(alpha))),
                upper_bound=float(min(args[2])) if len(args[2]) else float("inf"),
            )
        )
        return result

    listener = _Listener(record)
    level = core.LOGGER.level
    propagate = core.LOGGER.propagate
    core.OuterApproximationOptimizer._solve_milp = recorded
    core.LOGGER.addHandler(listener)
    core.LOGGER.setLevel(logging.INFO)
    # Recorded here rather than printed by whatever logs the rest of the run.
    core.LOGGER.propagate = False
    try:
        yield record
    finally:
        core.OuterApproximationOptimizer._solve_milp = original
        core.LOGGER.removeHandler(listener)
        core.LOGGER.setLevel(level)
        core.LOGGER.propagate = propagate


def margin_sensitivity(alphas: Sequence[ndarray], target: ndarray) -> ndarray:
    r"""Return how the margin moves each repaired cut at a box.

    The repair of cut $i$ replaces its slope $s_i$ by $s_i - D_i\mu_i$, with
    $D_i = [\alpha_j - \alpha_i]_j$ and $\mu_i$ the minimum-norm solution of
    $D_i^\top D_i \mu_i = r_i$, where $r_{ij}$ contains the margin $\delta$ once
    it is not clipped. The prediction of the cut at a box $\alpha$ therefore
    moves by $-\delta\,\mathbf{1}^\top (D_i^\top D_i)^+ D_i^\top(\alpha-\alpha_i)$.
    At a box already solved this is $-\delta$, which is what the margin is for;
    at any other box its sign is set by how $\alpha - \alpha_i$ decomposes over
    the boxes solved, and nothing makes it negative.

    Args:
        alphas: The one-hot encodings of the boxes solved.
        target: The one-hot encoding of the box to predict.

    Returns:
        The derivative of each cut's prediction at the box with respect to the
        margin, where the margin is not clipped. A positive value is a cut the
        margin *raises* there.
    """
    alphas = [array(alpha, dtype=float).ravel() for alpha in alphas]
    target = array(target, dtype=float).ravel()
    sensitivities = []
    for alpha in alphas:
        directions = array(alphas).T - alpha[:, None]
        weights = pinv(directions.T @ directions) @ (directions.T @ (target - alpha))
        sensitivities.append(-float(weights.sum()))

    return array(sensitivities)


def convexification_sensitivity(
    alphas: Sequence[ndarray], target: ndarray, n_components: int
) -> ndarray:
    r"""Return how the convexification constant moves each cut at a box.

    The convexification adds $\kappa\,\mathrm{scaling}\,(2\alpha_i - 1)$ to the
    slope of cut $i$, with a scaling of one over the number of components, so the
    prediction at $\alpha$ moves by
    $\frac{\kappa}{n}\sum_k (2\alpha_{ik} - 1)(\alpha_k - \alpha_{ik})$, which is
    $-2\kappa/n$ per component changed: never positive, zero at the box of the cut
    and growing with the distance.

    Args:
        alphas: The one-hot encodings of the boxes solved.
        target: The one-hot encoding of the box to predict.
        n_components: The number of subdivided components.

    Returns:
        The derivative of each cut's prediction at the box with respect to the
        constant.
    """
    target = array(target, dtype=float).ravel()
    return array([
        float((2 * array(alpha).ravel() - 1) @ (target - array(alpha).ravel()))
        / n_components
        for alpha in alphas
    ])


def repair_nonnegatively(
    alphas: Sequence[ndarray],
    slopes: Sequence[ndarray],
    values: Sequence[float],
    margin: float,
) -> list[ndarray]:
    r"""Repair the cut slopes as the master does, but with non-negative multipliers.

    This is ``_update_sensitivities_wt_secant_method`` of the master with one
    change: $\mu_i$ solves $D_i^\top D_i \mu_i = r_i$ by non-negative least
    squares instead of by the minimum-norm least squares. The right-hand side is
    the master's, $r_{ij} = \max(0, s_i^\top(\alpha_j-\alpha_i) - (v_j-v_i) +
    \delta)$; the bilateral variant of the master, which does not clip it, is not
    reproduced.

    Args:
        alphas: The one-hot encodings of the boxes solved.
        slopes: The slopes of their cuts.
        values: The values of the boxes.
        margin: The convexity margin $\delta$.

    Returns:
        The repaired slopes, in the order of the boxes.
    """
    encodings = [array(alpha, dtype=float).ravel() for alpha in alphas]
    values = array(values, dtype=float).ravel()
    repaired = []
    for alpha, slope, value in zip(encodings, slopes, values, strict=False):
        slope = array(slope, dtype=float).ravel()
        directions = array(encodings).T - alpha[:, None]
        rhs = slope @ directions - (values - value) + margin
        rhs[rhs < 0.0] = 0.0
        multipliers, _ = nnls(
            directions.T @ directions, rhs, maxiter=50 * max(len(rhs), 1)
        )
        repaired.append(slope - directions @ multipliers)

    return repaired


@contextmanager
def nonnegative_repair() -> Generator[None, None, None]:
    """Make the master repair its cuts with non-negative multipliers.

    For a measurement only: the change belongs to the master, and this replaces
    its method for the length of the context and restores it after.

    Yields:
        Nothing.
    """
    original = core.OuterApproximationOptimizer._update_sensitivities_wt_secant_method

    def repair(self, alpha_hist, slopes_hist, fopt_hist, min_dfk):  # noqa: ANN001, ANN202
        """Repair the slopes with non-negative multipliers."""
        del self
        return [
            atleast_2d(slope)
            for slope in repair_nonnegatively(
                alpha_hist, slopes_hist, fopt_hist, min_dfk
            )
        ]

    core.OuterApproximationOptimizer._update_sensitivities_wt_secant_method = repair
    try:
        yield
    finally:
        core.OuterApproximationOptimizer._update_sensitivities_wt_secant_method = (
            original
        )


def _optimal_box(n_components: int, n_subdivisions: int) -> ndarray:
    """Return the one-hot encoding of the box holding the origin from below.

    Args:
        n_components: The number of components.
        n_subdivisions: The subdivisions per component, an even number.

    Returns:
        The encoding.
    """
    alpha = zeros(n_components * n_subdivisions)
    alpha[
        [k * n_subdivisions + n_subdivisions // 2 - 1 for k in range(n_components)]
    ] = 1
    return alpha


def report(name: str, swept: bool, seed: int, n_subdivisions: int = 10) -> Record:
    """Run one row of Table D.12 and print why it stopped.

    Args:
        name: The problem.
        swept: Whether to sweep the convexity rather than calibrate it.
        seed: The seed of the starting point.
        n_subdivisions: The subdivisions per component.

    Returns:
        The record of the run.
    """
    dimension = 5
    density = (n_subdivisions,) * dimension
    budget = sum(density) * COST_PER_SUB_PROBLEM * HEADROOM
    problem = PROBLEMS[name]
    run = run_at_density_swept if swept else run_at_density
    with recording(n_subdivisions) as record:
        outcome = run(problem, dimension, density, seed, budget)

    gap = outcome.best - problem.optimum(dimension)
    label = "swept" if swept else "calibrated"
    stall = next(
        (
            message
            for message in reversed(record.messages)
            if "stopped changing" in message
        ),
        "",
    )
    print(
        f"\n{name}, {label}, seed {seed}: distance {gap:.4f}, cost {outcome.cost} "
        f"of {budget}, {len(record.iterations)} iterations, stopped by: "
        f"{'the budget' if outcome.truncated else record.termination} {stall}"
    )
    print(
        f"{'step':>6} {'radius':>7} {'probe':>6} {'rung':>8} {'box':>18}"
        f" {'eta':>9} {'UBD':>8} {'solved':>7}"
    )
    for solve in record.iterations[-1]:
        print(
            f"{solve.step:6.2f} {solve.radius:7.3f} {solve.probe:6d}"
            f" {solve.convexity:8.2f} {solve.box!s:>18} {solve.eta:9.3f}"
            f" {solve.upper_bound:8.4f} {'yes' if solve.repeated else 'no':>7}"
        )

    if record.last_call is not None:
        _, args, _ = record.last_call
        target = _optimal_box(dimension, n_subdivisions)
        if any((array(alpha).ravel() == target).all() for alpha in args[1]):
            print("the box holding the optimum has been solved")
            return record

        sensitivity = margin_sensitivity(args[1], target)
        print(
            "margin sensitivity of the cuts at the optimal box: "
            f"min {sensitivity.min():+.2f}, max {sensitivity.max():+.2f}, "
            f"{(sensitivity > 1e-9).sum()} of {len(sensitivity)} raised"
        )

    return record


ROWS: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("styblinski_tang", (2,) * 5),
    ("partly_multimodal", (10, 10, 1, 1, 1)),
    ("ackley", (10,) * 5),
    ("griewank", (19, 13, 11, 7, 9)),
    ("ackley", (63,) * 5),
    ("rastrigin", (10,) * 5),
)
"""The rows of Table D.12: each problem at the density its scans estimate."""


def measure(rows: Sequence[tuple[str, tuple[int, ...]]] = ROWS) -> None:
    """Print the swept rows of Table D.12 with the master's repair and with the fix.

    Args:
        rows: The problems and their densities.
    """
    print(f"{'problem':>18} {'density':>16} {'released repair':>24} {'fixed':>24}")
    for name, density in rows:
        problem = PROBLEMS[name]
        optimum = problem.optimum(len(density))
        budget = sum(density) * COST_PER_SUB_PROBLEM * HEADROOM
        cells = []
        for fixed in (False, True):
            gaps, costs = [], []
            for seed in SEEDS:
                with nonnegative_repair() if fixed else nullcontext():
                    outcome = run_at_density_swept(
                        problem, len(density), density, seed, budget
                    )
                gaps.append(outcome.best - optimum)
                costs.append(outcome.cost)
            cells.append(
                f"{median(gaps):.4f} · {median(costs):.0f} · "
                f"{sum(gap < 1e-2 for gap in gaps)}/{len(gaps)}"
            )
        print(
            f"{name:>18} {' '.join(map(str, density)):>16}"
            f" {cells[0]:>24} {cells[1]:>24}",
            flush=True,
        )


def main() -> None:
    """Report why the runs of Rastrigin stop, or measure the fix."""
    for name in ("gemseo", "gemseo_box_subdivision", ""):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    if sys.argv[1:] == ["measure"]:
        measure()
        return

    for swept in (True, False):
        for seed in SEEDS:
            report("rastrigin", swept, seed)


if __name__ == "__main__":
    main()
