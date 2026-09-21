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
an *equality* constraint on ``is_feasible``, and a box whose sub-problem has no
feasible point is cut on that rather than admitted.

The convexity margin reaches the master as ``min_dfk``, and the adaptive repair
compares it against **differences of objective value between solved boxes**::

    rhs = l_df_k - df_k + min_dfk

``df_k`` runs over the whole history the repair is given, which is the feasible
and the infeasible boxes **together**: an infeasible box still carries an
objective value and a slope, so it still produces an objective cut, and that cut
is repaired with the same margin. The scale to calibrate the margin against is
therefore the spread of the objective over **every box solved**, which is what
:func:`.objective_scale` reads and what the sweep uses.

What the margin does *not* reach is the ``is_feasible`` gate itself. The master
passes ``min_dfk`` to its inequality-constraint cuts but hard-codes ``0.0`` for
the equality ones, and the feasibility cut is an equality. So on a problem where
most boxes are infeasible, the margin still guards every objective cut, while
what decides **admissibility** is a mechanism no margin relaxes. A run that
returns nothing feasible is not a run whose margin was mis-scaled.

Which is the case for not calibrating a margin at all:
:class:`.SweptBoxSubdivisionSettings` reads the scale off the run, over every
box solved, and sweeps a ladder around it.

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
    """The spread of the objective over **every** box solved, zero below two.

    This is the scale the convexity margin is compared against, since the repair
    subtracts it from differences of objective value between solved boxes, and
    an infeasible box produces an objective cut like any other. It is the
    quantity :func:`.objective_scale` reads for the sweep.
    """

    @property
    def n_infeasible(self) -> int:
        """The number of boxes cut on feasibility rather than on their value."""
        return self.n_solved - self.n_feasible

    @property
    def margin_governs(self) -> bool:
        """Whether the convexity margin had anything to act on.

        The repair subtracts the margin from differences of objective value
        between solved boxes, so it takes two solved boxes -- of either kind,
        an infeasible one producing an objective cut like any other -- for the
        margin to enter the master at all.
        """
        return self.n_solved > 1

    @property
    def found_nothing_feasible(self) -> bool:
        """Whether the run admitted no box, which no margin can change.

        Admissibility is decided by the ``is_feasible`` gate, an equality
        constraint the master repairs with a margin of zero whatever
        ``convexity_margin`` says.
        """
        return self.n_feasible == 0

    def describe(self) -> str:
        """Return a one-line account of the run, in the terms of the margin.

        Returns:
            The account, naming how each box was cut.
        """
        counts = (
            f"{self.n_solved} boxes solved, {self.n_feasible} admitted and "
            f"{self.n_infeasible} cut on feasibility"
        )
        if not self.margin_governs:
            return (
                f"{counts}. The convexity margin is subtracted from differences "
                "of objective value between solved boxes, and fewer than two "
                "were solved, so it never entered the master."
            )

        scale = (
            f"{counts}; the objective spreads over {self.spread:.3g} across "
            "them, which is the scale to calibrate the convexity margin in"
        )
        if self.found_nothing_feasible:
            return (
                f"{scale}. No box was admitted, though: what rejects a box is "
                "the is_feasible gate, which the master repairs with a margin "
                "of zero whatever the convexity margin says, so no value of it "
                "would have admitted one."
            )

        return f"{scale}."


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
        # Over every box solved, which is the history the repair is given.
        spread=max(values) - min(values) if len(values) > 1 else 0.0,
    )


def log_margin_report(problem: OptimizationProblem) -> MarginReport:
    """Report what the convexity margin was doing, at the end of a run.

    A run that admitted no box is worth a warning: it is indistinguishable
    from a run the margin governed well, and the setting the tuning guidance
    sends a user to is not the one that would have admitted a box.

    Args:
        problem: The optimization problem of the master.

    Returns:
        The report, whether or not it warranted a warning.
    """
    report = read_margin_report(problem)
    if report.n_solved == 0:
        return report

    if report.margin_governs and not report.found_nothing_feasible:
        LOGGER.info("%s", report.describe())
    else:
        LOGGER.warning("%s", report.describe())

    return report
