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
r"""The convexity ladder, for a master that does not carry one yet.

**This module is temporary.** The sweep belongs to the master of the outer
approximation, and it is implemented there, in
``gemseo_bilevel_outer_approximation.algos.opt.core.convexity_sweep``. What is
here is the same policy, carried so that the stub of
``benchmarks/convexity_sweep.py`` can drive a released master that predates it.
:mod:`~gemseo_box_subdivision.convexity_sweep` prefers the master's own copy and
falls back to this one, so **delete this module** once the sweep ships upstream.

The API is upstream's, deliberately, so that the stub behaves the same against
either. See that module, and
[annex C](../algorithm/tuning.md), for what the ladder is and why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from numpy import geomspace
from numpy import isfinite

if TYPE_CHECKING:
    from collections.abc import Iterable

LADDER_DECADES: float = 2.0
r"""The number of decades a ladder spans below its upper bound.

Two decades covers the range over which the behaviour of either mechanism
changes: over an objective spanning about eighty, a margin of $1$ leaves the
cuts unusable and a margin of $100$ saturates. A ladder from
$\kappa_{\max} / 100$ to $\kappa_{\max}$ therefore holds both the rung that
explores and the rungs that exploit, whatever the scale of the objective.
"""

HEADROOM: float = 10.0
"""The factor applied to an upper bound read off the objective.

The spread of the objective over the boxes **already solved** is a lower estimate
of its spread over the design space, and badly so early in a run, when the boxes
solved are the handful the first iterations proposed. Reading the bound off it
without headroom is circular: the scale that would buy the exploration is the one
the exploration would reveal, and a landscape whose first boxes look alike never
escapes them.

A factor is dimensionless, so it transfers between problems where an absolute
margin does not, and erring high on it costs the probes of the low rungs rather
than the result.
"""


def convexity_ladder(
    max_value: float, n_points: int, decades: float = LADDER_DECADES
) -> tuple[float, ...]:
    r"""Return the rungs of a convexity ladder.

    The rungs are geometric from $\kappa_{\max} / 10^{\text{decades}}$ up to
    $\kappa_{\max}$, the upper bound being the last one, so that a ladder of a
    single point is the single value it would replace.

    Args:
        max_value: The upper bound of the sweep, in the units of the objective.
        n_points: The number of rungs.
        decades: The number of decades the ladder spans below ``max_value``.

    Returns:
        The rungs, in increasing order.

    Raises:
        ValueError: When the upper bound is not positive, when the number of
            rungs is not positive, or when the span is negative.
    """
    if max_value <= 0.0:
        msg = f"The upper bound of the sweep must be positive; got {max_value}."
        raise ValueError(msg)

    if n_points < 1:
        msg = f"The number of rungs must be positive; got {n_points}."
        raise ValueError(msg)

    if decades < 0.0:
        msg = f"The span of the ladder must be non-negative; got {decades}."
        raise ValueError(msg)

    if n_points == 1:
        return (float(max_value),)

    rungs = geomspace(max_value / 10.0**decades, max_value, num=n_points)
    return tuple(float(rung) for rung in rungs)


def objective_scale(values: Iterable[float]) -> float:
    """Return the variation of the objective over the values observed so far.

    Both mechanisms are calibrated against the same quantity, the non-convexity
    they have to dominate, whose order is the variation of the objective over the
    design space. The master observes that variation as it solves sub-problems,
    so the upper bound of a sweep needs no user at all, once corrected by the
    headroom that a partial observation calls for.

    Args:
        values: The objective values of the sub-problems already solved.

    Returns:
        The spread of the finite values among them, or ``0.0`` when fewer than
        two of them are finite, which is not yet a scale.
    """
    finite = [float(value) for value in values if isfinite(value)]
    if len(finite) < 2:
        return 0.0

    return max(finite) - min(finite)


@dataclass(frozen=True)
class ConvexitySweep:
    """A ladder of convexity values, and the rungs each probe deploys.

    This is a policy rather than an optimizer: it says which value the master
    should be given next, and knows nothing of the master itself.
    """

    ladder: tuple[float, ...]
    """The rungs of the ladder, in increasing order."""

    def __post_init__(self) -> None:
        """Check the ladder.

        Raises:
            ValueError: When the ladder is empty or is not increasing.
        """
        if not self.ladder:
            msg = "The ladder of the sweep is empty."
            raise ValueError(msg)

        if any(
            second <= first
            for first, second in zip(self.ladder, self.ladder[1:], strict=False)
        ):
            msg = f"The rungs of the ladder must increase; got {list(self.ladder)}."
            raise ValueError(msg)

    @classmethod
    def from_bounds(
        cls, max_value: float, n_points: int, decades: float = LADDER_DECADES
    ) -> ConvexitySweep:
        """Return the sweep of an upper bound and a number of points.

        Args:
            max_value: The upper bound of the sweep, in the units of the
                objective.
            n_points: The number of rungs.
            decades: The number of decades the ladder spans below ``max_value``.

        Returns:
            The sweep.
        """
        return cls(convexity_ladder(max_value, n_points, decades))

    @property
    def n_points(self) -> int:
        """The number of rungs, hence of probes."""
        return len(self.ladder)

    @property
    def max_value(self) -> float:
        """The upper bound of the sweep, the top rung."""
        return self.ladder[-1]

    def rungs(self, index: int) -> tuple[float, ...]:
        """Return the rungs a probe deploys, in the order it deploys them.

        A probe starts at the rung of its own index, which is what makes an
        iteration span the ladder, and climbs from there. The probe at the top
        rung has nowhere to climb, so a box it does not propose is a box no probe
        will propose.

        Args:
            index: The index of the probe, from zero. An index past the ladder
                is clamped to its top rung, the conservative end, which is where
                a probe with no rung of its own belongs.

        Returns:
            The rungs, the probe's own first.
        """
        return self.ladder[min(max(index, 0), self.n_points - 1) :]

    def probe_index(self, n_probes: int, probe: int) -> int:
        """Return the rung a probe starts from.

        The probes and the rungs need not be equal in number: the probes spread
        over the ladder, so that the tight trust region and the raw cuts explore
        together and the wide region and the dominated cuts do too.

        A master with nowhere to spread its probes gets the **top** rung. A lone
        probe at the bottom is a run with its cuts unguarded, which converges
        after two or three sub-problems and reports success far from the optimum,
        and a single value belongs at the conservative end of the ladder.

        Args:
            n_probes: The number of parallel points of the master.
            probe: The index of the probe, from zero.

        Returns:
            The index of the rung the probe starts from.
        """
        if n_probes <= 1:
            return self.n_points - 1

        return min(probe * self.n_points // n_probes, self.n_points - 1)
