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
"""Sweeping the convexity from outside a master that does not sweep by itself.

The sweep belongs to the master: it varies a setting **per probe and per
iteration**, which only the loop owning the probes can do, and only the master
observes the objective the unbounded form reads its bound off. Where the master
implements it, :data:`.MASTER_SWEEPS_CONVEXITY` is ``True`` and nothing here
runs.

Where it does not, the alternative is not "no sweep": it is a run given no
convexity at all, since a swept run has no calibrated value to fall back on and
the master's own default is zero, which leaves the cuts unguarded. So this drives
the ladder from outside, around the master's mixed-integer solve, computing the
bound from the objective exactly as the master would.

This module is **temporary**, like :mod:`.._convexity_sweep_fallback`: both go
when the master ships the sweep, and nothing else in the package depends on the
patching they do.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any

from gemseo_bilevel_outer_approximation.algos.opt.core import (
    outer_approximation_optimizer as core,
)
from numpy import argmin
from numpy import atleast_2d
from numpy import geomspace

from gemseo_box_subdivision import convexity_sweep as policy
from gemseo_box_subdivision.convexity_sweep import ConvexitySweep
from gemseo_box_subdivision.convexity_sweep import objective_scale

if TYPE_CHECKING:
    from collections.abc import Iterator

_FOPT_HIST = 2
"""Where the objective history sits among the positional arguments of the solve."""

_CURRENT_STEP = 14
"""Where the radius of the probe sits among them."""


@dataclass(frozen=True)
class Deployment:
    """One probe that proposed a box not yet solved.

    The master keeps no such record, so this exists only to report what the
    sweep did: which rung a box came from, and whether the probe had to climb to
    get it.
    """

    index: int
    """The index of the probe, and of the rung it started from."""

    value: float
    """The rung that produced the proposal, at or above the probe's own."""

    proposal: Any
    """What the master proposed at that rung."""

    starting_value: float = 0.0
    """The rung the probe started from."""

    @property
    def escalated(self) -> bool:
        """Whether the probe had to climb above its own rung to propose a box."""
        return self.value > self.starting_value


def _probe(optimizer: Any, current_step: float | None) -> int:
    """Return which of its parallel probes the master is calling for.

    The master does not say: it says which trust-region radius the probe was
    given, out of the ``geomspace(step / 2, step)`` it spreads them over, so the
    probe is recovered from the radius. Mapping it onto a rung is then the
    master's own rule, :meth:`.ConvexitySweep.probe_index`, and it pairs the two
    ladders: the tight region and the raw cuts exploit together, the wide region
    and the dominated cuts explore together.

    Args:
        optimizer: The master.
        current_step: The radius the probe was given, if any.

    Returns:
        The index of the probe. A solve made outside the probing loop passes the
        radius of the master itself, the top of the radius ladder, and so lands
        on the last probe, whose rung is the conservative end.
    """
    n_points = optimizer.n_parallel_points
    if n_points <= 1 or current_step is None:
        return n_points - 1

    steps = geomspace(
        max(optimizer.current_step / 2, optimizer.min_step),
        optimizer.current_step,
        num=n_points,
    )
    return int(argmin(abs(steps - current_step)))


@contextmanager
def drive_the_sweep(
    max_value: float, setting_name: str = "min_dfk"
) -> Iterator[list[Deployment]]:
    """Make the parallel probes of the master sweep the convexity setting.

    The ladder has one rung per parallel point of the master, read off the master
    itself, which is what pairs a probe with a rung; a rung count of its own could
    disagree with the probes it is spread over.

    Args:
        max_value: The upper bound of the sweep, or zero to read it off the
            objective as the run observes it.
        setting_name: The setting the mechanism calibrates, ``"min_dfk"`` for the
            adaptive repair and ``"convexification_constant"`` for the pure
            convexification. The two are never active at once, so the sweep
            varies one of them.

    Yields:
        The deployments that proposed a box not yet solved, appended as the run
        goes, so that a caller can report which rungs the boxes came from.
    """
    original = core.OuterApproximationOptimizer._solve_milp
    trace: list[Deployment] = []

    def patched(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        """Solve the master at the rung of this probe, climbing while it repeats.

        Args:
            *args: The arguments of the master.
            **kwargs: The keyword arguments of the master.

        Returns:
            Whatever the master returns, at the rung that proposed a new box or
            at the top of the ladder.
        """
        fopt_hist = (
            args[_FOPT_HIST] if len(args) > _FOPT_HIST else kwargs.get("fopt_hist", ())
        )
        current_step = kwargs.get(
            "current_step", args[_CURRENT_STEP] if len(args) > _CURRENT_STEP else None
        )
        # policy.HEADROOM rather than a name bound at import: the benchmark
        # patches the module to measure what the headroom buys.
        bound = max_value or objective_scale(fopt_hist) * policy.HEADROOM
        sweep = (
            ConvexitySweep.from_bounds(bound, self.n_parallel_points)
            if bound > 0.0
            else None
        )
        if sweep is None:
            # Nothing has been solved yet, so the objective has no scale to read
            # the upper bound off: leave the master its own value.
            return original(self, *args, **kwargs)

        index = sweep.probe_index(self.n_parallel_points, _probe(self, current_step))
        result = None
        try:
            for value in sweep.rungs(index):
                setattr(self, setting_name, value)
                result = original(self, *args, **kwargs)
                alpha, _, is_feasible = result
                if not is_feasible:
                    # The master is infeasible on its trust region and its
                    # eliminated boxes, neither of which the convexity enters:
                    # a higher rung cannot make it feasible again.
                    break

                if not self._is_previously_computed(atleast_2d(alpha)):
                    trace.append(
                        Deployment(
                            index=index,
                            value=value,
                            proposal=tuple(alpha.flatten().tolist()),
                            starting_value=sweep.ladder[index],
                        )
                    )
                    break
        finally:
            # The conservative end, which is where the master leaves it too:
            # every solve made outside the sweep, such as the elimination of a
            # point the ladder could not get past, belongs at the top rung rather
            # than at a low one, which would leave the cuts unguarded.
            setattr(self, setting_name, sweep.max_value)

        return result

    core.OuterApproximationOptimizer._solve_milp = patched
    try:
        yield trace
    finally:
        core.OuterApproximationOptimizer._solve_milp = original
