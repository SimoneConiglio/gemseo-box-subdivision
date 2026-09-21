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
r"""What the convexity margin was doing, read back from a run.

A constraint declared with ``main_level=True`` does not reach the master as a
constraint. It reaches it as a **feasibility cut**: the formulation adds, once,
a constraint on ``is_feasible``, and a box whose sub-problem has no feasible
point is cut on that rather than on its objective value.

The convexity margin reaches the master as ``min_dfk``, which relaxes the
**objective** cuts. Nothing relaxes the feasibility cuts, and nothing should: a
box holding no feasible point genuinely holds none, whatever the convexity of
the objective. A box is cut on feasibility *exactly*.

The consequence is worth reporting rather than leaving to be discovered. On a
problem where most boxes are infeasible, what decides which boxes stay
admissible is the feasibility cuts, so the one setting the tuning guidance
directs a user to has little or no purchase on their run. The margin is
calibrated against the objective, and the objective is not what is steering.

This module reads that off a finished run, from the database of the **master**,
which carries one entry per box solved with its value and its ``is_feasible``
flag.

:::{warning}
The database of the *sub-problem* is not a record of the boxes. Under the
normalized formulation the sub-problem solves for the normalized coordinate of
its box, so every box writes to the same keys — the centre of every box is
``0.5`` — and a later box overwrites an earlier one. Counting feasible points
there reports the last box solved rather than the run.
:::
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from numpy import ravel

if TYPE_CHECKING:
    from gemseo.algos.optimization_problem import OptimizationProblem

LOGGER = logging.getLogger(__name__)

IS_FEASIBLE_NAME: str = "is_feasible"
"""The name under which the master records whether a box held a feasible point."""


@dataclass(frozen=True)
class MarginReport:
    """What a finished run says about the guard the margin provides."""

    n_solved: int
    """The number of boxes whose sub-problem the master solved."""

    n_feasible: int
    """The number of those boxes that held a feasible point."""

    best_feasible: float | None
    """The best objective value over the feasible boxes, or ``None`` if none."""

    spread: float
    """The spread of the objective over the feasible boxes, zero below two."""

    @property
    def n_infeasible(self) -> int:
        """The number of boxes cut on feasibility rather than on their value."""
        return self.n_solved - self.n_feasible

    @property
    def margin_governs(self) -> bool:
        """Whether the convexity margin could have governed the exploration.

        The margin relaxes the objective cuts against one another, so it takes
        two feasible boxes for it to have anything to act on. A run below that
        was steered by its feasibility cuts, which the margin does not reach.
        """
        return self.n_feasible > 1

    def describe(self) -> str:
        """Return a one-line account of the run, in the terms of the margin.

        Returns:
            The account, naming how each box was cut.
        """
        counts = (
            f"{self.n_solved} boxes solved, {self.n_feasible} feasible and "
            f"{self.n_infeasible} cut on feasibility"
        )
        if not self.margin_governs:
            return (
                f"{counts}. The convexity margin relaxes the objective cuts, "
                "and fewer than two boxes produced one, so what steered this "
                "run was the feasibility cuts, which no margin relaxes: "
                "calibrating the margin against the objective cannot change it."
            )

        return (
            f"{counts}; the objective spreads over {self.spread:.3g} across the "
            "feasible boxes, which is the scale the convexity margin is "
            "calibrated in."
        )


def read_margin_report(problem: OptimizationProblem) -> MarginReport:
    """Return what the convexity margin was doing over a finished run.

    Args:
        problem: The optimization problem of the master, whose database carries
            one entry per box solved. Not the sub-problem's, whose keys are the
            normalized coordinates of a box and are shared between boxes.

    Returns:
        The report.
    """
    name = problem.objective.name
    values = []
    feasible = []
    for entry in problem.database.values():
        value = entry.get(name)
        if value is None:
            continue

        value = float(ravel(value)[0])
        values.append(value)
        flag = entry.get(IS_FEASIBLE_NAME)
        # Without a main-level constraint the master records no flag, and every
        # box it solved is a box that produced an objective cut.
        if flag is None or float(ravel(flag)[0]) > 0.5:
            feasible.append(value)

    return MarginReport(
        n_solved=len(values),
        n_feasible=len(feasible),
        best_feasible=min(feasible) if feasible else None,
        spread=max(feasible) - min(feasible) if len(feasible) > 1 else 0.0,
    )


def log_margin_report(problem: OptimizationProblem) -> MarginReport:
    """Report what the convexity margin was doing, at the end of a run.

    A run the margin cannot have governed is worth a warning: it is
    indistinguishable from a run it governed well, and the setting the tuning
    guidance sends a user to is not the one deciding it.

    Args:
        problem: The optimization problem of the master.

    Returns:
        The report, whether or not it warranted a warning.
    """
    report = read_margin_report(problem)
    if report.n_solved == 0:
        return report

    if report.margin_governs:
        LOGGER.info("%s", report.describe())
    else:
        LOGGER.warning("%s", report.describe())

    return report
