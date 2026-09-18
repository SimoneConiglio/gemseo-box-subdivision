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

This module is **temporary**, like
:mod:`~gemseo_box_subdivision._convexity_sweep_fallback`: both go when the master
ships the sweep, and nothing else in the package depends on the patching they
do.
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

from gemseo_box_subdivision.convexity_sweep import objective_scale

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Iterator

    from gemseo_box_subdivision.settings import SweptBoxSubdivisionSettings

_FOPT_HIST = 2
"""Where the objective history sits among the positional arguments of the solve."""

_INFEASIBLE_FOPT_HIST = 12
"""Where the objective of the boxes found infeasible sits among them."""

_CURRENT_STEP = 14
"""Where the radius of the probe sits among them."""


def _argument(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    index: int,
    name: str,
    default: Any = None,
) -> Any:
    """Return one argument of the solve, however the master passed it.

    The default is returned rather than tested for afterwards: an objective
    history may be an array, and asking whether an array is empty by its truth
    value raises rather than answering.

    Args:
        args: The positional arguments.
        kwargs: The keyword arguments.
        index: The position of the argument.
        name: Its name.
        default: What to return where the master passed neither.

    Returns:
        The argument, or the default.
    """
    if len(args) > index:
        return args[index]

    return kwargs.get(name, default)


@dataclass(frozen=True)
class Deployment:
    """One probe that proposed a box not yet solved.

    The master keeps no such record, so this exists only to report what the
    sweep did: which rung a box came from, and whether the probe had to climb to
    get it.
    """

    index: int
    """The index of the **rung** the probe started from.

    Not the index of the probe: :meth:`.ConvexitySweep.probe_index` maps one onto
    the other, and exists because the two counts need not agree.
    """

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

    lowest = max(optimizer.current_step / 2, optimizer.min_step)
    if lowest >= optimizer.current_step:
        # The trust region has shrunk onto its floor, so every probe is given the
        # same radius and none of them can be told from another. They are not all
        # the bottom rung, which is where ``argmin`` would put them and which is
        # the least guarded end: an unidentifiable probe takes the top rung, as a
        # lone probe does.
        return n_points - 1

    steps = geomspace(lowest, optimizer.current_step, num=n_points)
    return int(argmin(abs(steps - current_step)))


def _history(
    args: tuple[Any, ...], kwargs: dict[str, Any], index: int, name: str
) -> Iterable[float]:
    """Return one objective history of the solve, empty where there is none.

    Neither absence nor ``None`` is asked about by truth value: a history may be
    an array, and an array has no truth value to ask for.

    Args:
        args: The positional arguments.
        kwargs: The keyword arguments.
        index: The position of the history.
        name: Its name.

    Returns:
        The history, or an empty one.
    """
    history = _argument(args, kwargs, index, name)
    if history is None:
        return ()

    return history


_ADAPTIVE_GATE = "use_adaptative_convexification"
"""The attribute behind which the master reads the convexity margin.

The margin is read only where the adaptive repair is on, so a swept run whose
master was configured elsewhere, and left it off, would sweep a number the master
never looks at.
"""

_DRIVING: list[Any] = []
"""The sweeps whose contexts are open, in the order they were entered.

Only the last of them drives: a context entered inside another is the run's, and
two ladders over one solve would have the outer one set the rung after the inner
one did, so the inner ladder would be reported and the outer one solved. A sweep
that is not in this list at all has had its context ended.
"""

_DELEGATE = "_sweep_delegate"
"""The attribute under which a wrapper keeps what it wraps.

A wrapper is a plain function put on the class, so the chain of them has to be
carried on the wrappers themselves: the class attribute names only the last one
installed.
"""


def _unpatch(patched: Any) -> None:
    """Take one wrapper out of the chain, whatever was installed over it.

    Restoring the class attribute is right only where this wrapper is still the
    one installed. Where another context patched over it and has not left yet,
    putting back what this one wrapped would undo that context as well; and
    leaving the attribute alone is not enough either, since the wrapper above
    still delegates to this one and would keep it running after its context
    ended. So the wrapper above is made to delegate to what this one wrapped, and
    the chain closes over it.

    A wrapper this module did not install cannot be spliced, since nothing says
    what it delegates to; the sweep is then left in place and stops sweeping by
    itself, its context having ended.

    Args:
        patched: The wrapper to remove.
    """
    if core.OuterApproximationOptimizer._solve_milp is patched:
        core.OuterApproximationOptimizer._solve_milp = getattr(patched, _DELEGATE)
        return

    wrapper = core.OuterApproximationOptimizer._solve_milp
    while (delegate := getattr(wrapper, _DELEGATE, None)) is not None:
        if delegate is patched:
            setattr(wrapper, _DELEGATE, getattr(patched, _DELEGATE))
            return

        wrapper = delegate


@contextmanager
def drive_the_sweep(
    settings: SweptBoxSubdivisionSettings,
) -> Iterator[list[Deployment]]:
    """Make the parallel probes of the master sweep the convexity setting.

    The ladder has one rung per parallel point of the master, read off the master
    itself, which is what pairs a probe with a rung; a rung count of its own could
    disagree with the probes it is spread over. The settings say what the ladder
    is bounded by and which setting the mechanism calibrates.

    Args:
        settings: The swept construction this run was given.

    Yields:
        The deployments that proposed a box not yet solved, appended as the run
        goes, so that a caller can report which rungs the boxes came from.
    """
    setting_name = settings.convexity_setting_name
    gated = settings.mechanism == "adaptive"
    switched_off = "convexification_constant" if gated else "min_dfk"
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
        if not _DRIVING or _DRIVING[-1] is not patched:
            # This context has ended, or a sweep entered inside it is the run's:
            # either way the solve goes straight through, since a wrapper left in
            # the chain that still set a rung would overwrite the rung of the
            # sweep that is driving.
            return getattr(patched, _DELEGATE)(self, *args, **kwargs)

        # The master reads the margin only where the adaptive repair is on, and
        # the constant wherever it is positive, and a run that configured its
        # master itself may have left the repair off or the constant standing.
        # Choosing one mechanism switches the other off, on the master as in the
        # settings: what the run needs of its master is not what a caller
        # overrides, and the two mechanisms are never combined.
        setattr(self, _ADAPTIVE_GATE, gated)
        setattr(self, switched_off, 0.0)
        # Every box that has been solved carries a scale, the infeasible ones
        # included: the sooner two of them differ, the sooner the ladder exists
        # and the fewer solves the master makes at its own value, which is zero.
        solved = (
            *_history(args, kwargs, _FOPT_HIST, "fopt_hist"),
            *_history(args, kwargs, _INFEASIBLE_FOPT_HIST, "infeasible_fopt_hist"),
        )
        current_step = _argument(args, kwargs, _CURRENT_STEP, "current_step")
        # The settings build the ladder, from the probes this master actually
        # runs: one rung per probe is the construction, and counting them here
        # as well is how the two came to disagree.
        sweep = settings.create_sweep(objective_scale(solved), self.n_parallel_points)
        if sweep is None:
            # Nothing has been solved yet, so the objective has no scale to read
            # the upper bound off: leave the master its own value.
            return getattr(patched, _DELEGATE)(self, *args, **kwargs)

        index = sweep.probe_index(self.n_parallel_points, _probe(self, current_step))
        result = None
        try:
            for value in sweep.rungs(index):
                setattr(self, setting_name, value)
                result = getattr(patched, _DELEGATE)(self, *args, **kwargs)
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

    setattr(patched, _DELEGATE, original)
    core.OuterApproximationOptimizer._solve_milp = patched
    _DRIVING.append(patched)
    try:
        yield trace
    finally:
        _DRIVING.remove(patched)
        _unpatch(patched)
