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
r"""Relaxing the constraint cuts of the master, as the objective's are relaxed.

A constraint of the original problem declared at the main level reaches the
master as a **cut of its own**, linearized in the one-hot variables. Such a cut
is an outer approximation of the constraint only while the constraint is convex
over the boxes; where it is **concave** the linearization lies above it, so the
cut excludes boxes the constraint admits and the master stops steering towards a
region it has already cut away.

That is the same failure the objective's cuts have on a multimodal problem, and
it has the same two answers -- the adaptive repair with a margin, and the
convexification -- neither of which the released master applies to a constraint
cut on its own terms:

============================ ====================== ==================
cut                          adaptive               convexification
============================ ====================== ==================
objective                    ``min_dfk``            applied
master inequality constraint ``min_dfk``            *commented out*
master equality constraint   hard-coded ``0.0``     *commented out*
============================ ====================== ==================

The inequality row is not the objective's margin being reused by design: a
constraint is not in the units of the objective, so a value that guards one
cannot guard the other, and the measurement in the tests shows the objective
margin having to be raised a hundredfold to open a box a constraint margin opens
at one.

This module supplies what the master does not, around its mixed-integer solve
and without changing it, exactly as
:mod:`~gemseo_box_subdivision._convexity_sweep_driver` supplies the sweep. Both
are temporary, and both go the day the master ships the mechanism.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any

from numpy import atleast_2d
from numpy import ndarray

if TYPE_CHECKING:
    from collections.abc import Iterator
    from collections.abc import Sequence

    from gemseo_box_subdivision.settings import BaseBoxSubdivisionSettings

_CONSTRAINT_HISTORIES = "_gemseo_box_subdivision_constraint_alpha_histories"
"""Where a solve records the histories that are a constraint's rather than the objective's."""  # noqa: E501


def _is_constraint_history(optimizer: Any, alpha_hist: Any) -> bool:
    """Return whether a history is a constraint's rather than the objective's.

    The master hands the same list objects it received to the repair, so the
    histories are told apart by **identity**: the objective's calls pass
    ``alpha_hist``, ``infeasible_alpha_hist`` or a fresh concatenation of the
    two, none of which is either constraint list.

    Args:
        optimizer: The master.
        alpha_hist: The history the repair was called with.

    Returns:
        Whether it is one of the constraint histories of the solve in progress.
    """
    return any(
        alpha_hist is history
        for history in getattr(optimizer, _CONSTRAINT_HISTORIES, ())
    )


def _convexify(
    optimizer: Any,
    alpha_hist: Sequence[Any],
    jacobians: Sequence[ndarray],
    value: float,
) -> list[ndarray]:
    """Return the constraint jacobians with the convexification added.

    The master's own routine is used, under the constraint's constant rather
    than the objective's, so that the term a constraint cut receives is the one
    a constraint cut was given a setting for. A constraint of several components
    has a jacobian per component, which the routine reads one row at a time.

    Args:
        optimizer: The master.
        alpha_hist: The one-hot vector each cut was taken at.
        jacobians: The jacobian of each cut.
        value: The convexification constant of the constraints.

    Returns:
        The jacobians, convexified.
    """
    original = optimizer.convexification_constant
    optimizer.convexification_constant = value
    try:
        convexified = []
        for alpha, jacobian in zip(alpha_hist, jacobians, strict=False):
            rows = atleast_2d(jacobian)
            updated = [
                optimizer._update_sensitivities_posa_convexification(  # noqa: SLF001
                    [alpha], [row]
                )[0]
                for row in rows
            ]
            # One row in, one row out: a cut of one component keeps the shape
            # the master gave it, which is what its assembly branches on.
            convexified.append(
                atleast_2d(jacobian).__class__(
                    updated[0] if len(updated) == 1 else [row[0] for row in updated]
                )
                if len(updated) > 1
                else updated[0].reshape(jacobian.shape)
            )

        return convexified
    finally:
        optimizer.convexification_constant = original


@contextmanager
def relax_the_constraints(settings: BaseBoxSubdivisionSettings) -> Iterator[None]:
    """Give the constraint cuts of the master the relaxation the settings ask for.

    Args:
        settings: The settings of the run, naming the mechanism and the value
            the constraints are relaxed by.

    Yields:
        Nothing.
    """
    margin, constant = settings.constraint_relaxation
    if not margin and not constant:
        yield
        return

    # Imported here, so that a package that never relaxes a constraint cut never
    # imports the master's internals.
    from gemseo_bilevel_outer_approximation.algos.opt.core import (  # noqa: PLC0415
        outer_approximation_optimizer as core,
    )

    optimizer_class = core.OuterApproximationOptimizer
    solve = optimizer_class._solve_milp  # noqa: SLF001
    repair = optimizer_class._update_sensitivities_wt_secant_method  # noqa: SLF001
    build = optimizer_class._build_milp_problem  # noqa: SLF001
    build_relaxed = optimizer_class._build_relaxed_milp_problem  # noqa: SLF001

    def patched_solve(
        self: Any,
        slopes_hist: Any,
        alpha_hist: Any,
        fopt_hist: Any,
        ineq_constr_alpha: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        eq_constr_alpha = args[2] if len(args) > 2 else kwargs["eq_constr_alpha"]
        # The histories of this solve, so that the repair can tell a constraint
        # cut from an objective cut without the master having to say which.
        setattr(self, _CONSTRAINT_HISTORIES, (ineq_constr_alpha, eq_constr_alpha))
        try:
            return solve(
                self,
                slopes_hist,
                alpha_hist,
                fopt_hist,
                ineq_constr_alpha,
                *args,
                **kwargs,
            )
        finally:
            setattr(self, _CONSTRAINT_HISTORIES, ())

    def patched_repair(
        self: Any,
        alpha_hist: Any,
        slopes_hist: Any,
        fopt_hist: Any,
        min_dfk: float,
    ) -> Any:
        if _is_constraint_history(self, alpha_hist):
            # The margin of the constraints, in their units: what the master
            # passes here is the objective's, or nothing at all for an equality.
            min_dfk = margin

        return repair(self, alpha_hist, slopes_hist, fopt_hist, min_dfk)

    def _convexified(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[Any, ...]:
        """Return the arguments with the constraint jacobians convexified."""
        values = list(args)
        # (self, slopes, alpha, fopt, ineq_alpha, ineq_viol, ineq_jac,
        #  eq_alpha, eq_viol, eq_jac, ...)
        for alpha_index, jacobian_index in ((4, 6), (7, 9)):
            if len(values) > jacobian_index and values[jacobian_index] is not None:
                values[jacobian_index] = _convexify(
                    values[0], values[alpha_index], values[jacobian_index], constant
                )

        return tuple(values)

    def patched_build(*args: Any, **kwargs: Any) -> Any:
        return build(*_convexified(args, kwargs), **kwargs)

    def patched_build_relaxed(*args: Any, **kwargs: Any) -> Any:
        return build_relaxed(*_convexified(args, kwargs), **kwargs)

    optimizer_class._solve_milp = patched_solve  # noqa: SLF001
    optimizer_class._update_sensitivities_wt_secant_method = patched_repair  # noqa: SLF001
    if constant:
        optimizer_class._build_milp_problem = patched_build  # noqa: SLF001
        optimizer_class._build_relaxed_milp_problem = patched_build_relaxed  # noqa: SLF001

    try:
        yield
    finally:
        optimizer_class._solve_milp = solve  # noqa: SLF001
        optimizer_class._update_sensitivities_wt_secant_method = repair  # noqa: SLF001
        optimizer_class._build_milp_problem = build  # noqa: SLF001
        optimizer_class._build_relaxed_milp_problem = build_relaxed  # noqa: SLF001
