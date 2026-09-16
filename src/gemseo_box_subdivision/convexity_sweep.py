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
r"""Sweeping the convexity setting in parallel, instead of choosing it.

The convexity margin ``min_dfk`` and the convexification constant are absolute
quantities in the units of the objective, and annex C of the documentation says
neither transfers between problems: a margin of :math:`100` reaches the optimum
from every starting point on an objective spanning eighty, and is the worst of
those tried on one spanning twenty-two. That the user has to supply a number
calibrated against a quantity they do not know is the standing criticism of the
method, and it is not answered by a better default.

It is answered by **not choosing**. The master already probes several
trust-region radii per iteration, one per parallel point, over
``geomspace(step / 2, step)``: the parallel points are a sweep, not a batch. This
module does the same for the convexity setting, so that one iteration deploys a
**ladder** of values rather than a single one.

What that buys is the two regimes at once, in one iteration. At the bottom rung
the cuts are left near their raw slopes, the master trusts its model, and the
proposal sits near the incumbent, which is the exploitation. At the top rung the
correction dominates the concavity, every unexplored box outranks the incumbent,
and the proposal is far away, which is the exploration.

A probe whose rung proposes **no new box** is not wasted: it is redeployed one
rung up, and again, until it proposes a box that has not been solved or the
ladder is exhausted. Exhaustion of every probe is the stopping criterion, and it
is a stronger statement than the one a single value supports: *no value up to*
:math:`\kappa_{\max}` *proposes anything new*, rather than *the one value tried
does not*.

The user then supplies an **upper bound** and a **number of points**, both of
which the criticism tolerates: erring high on the bound costs sub-problems rather
than quality, since the low rungs remain on the ladder either way. And the bound
itself has an observable default, :func:`.objective_scale`: the spread of the
objective over the boxes already solved, which is the very quantity both
mechanisms are calibrated against.

.. note::
    The policy here is deliberately free of GEMSEO: it is a ladder and an
    escalation rule, so that it can be tested on its own and moved into
    ``gemseo-bilevel-outer-approximation``, where the loop it belongs to lives.
    What drives it against the real master is the stub of
    ``benchmarks/convexity_sweep.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any

from numpy import geomspace
from numpy import isfinite

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Iterable

LADDER_DECADES: float = 2.0
r"""The number of decades the ladder spans below its upper bound.

Two decades is what the sweeps of annex C cover: over an objective spanning about
eighty, the margin reaches the optimum from one starting point out of eight at
:math:`1`, five at :math:`10`, seven at :math:`30` and all eight at :math:`100`.
A ladder from :math:`\kappa_{\max} / 100` to :math:`\kappa_{\max}` therefore
holds both the rung that explores and the rungs that exploit, whatever the scale
of the objective.
"""

N_CONVEXITY_POINTS: int = 4
"""The default number of rungs of the ladder.

The same count as the parallel points of the master, so that a probe per rung
costs what the parallel probing already costs.
"""

HEADROOM: float = 10.0
"""The factor applied to an upper bound read off the objective.

The spread of the objective over the boxes **already solved** is a lower estimate
of its spread over the design space, and badly so early in a run, when the boxes
solved are the handful the first iterations proposed. Reading the bound off it
without headroom is circular: the scale that would buy the exploration is the one
the exploration would reveal, and a landscape whose first boxes look alike, such
as Ackley, never escapes.

A factor is not the quantity the criticism is about. It is **dimensionless**, so
it transfers between problems where an absolute margin does not, and erring high
on it costs the probes of the low rungs rather than the result. One decade is
what the measurement of ``benchmarks/convexity_sweep.py`` supports, on the two
problems it reports.
"""


def convexity_ladder(
    max_value: float, n_points: int, decades: float = LADDER_DECADES
) -> tuple[float, ...]:
    r"""Return the rungs of a convexity ladder.

    The rungs are geometric from :math:`\kappa_{\max} / 10^{\text{decades}}` up
    to :math:`\kappa_{\max}`, the upper bound being the last one, so that a
    ladder of a single point is the single value it would replace.

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

    Both mechanisms of the master are calibrated against the same quantity, the
    non-convexity they have to dominate, whose order is the variation of the
    objective over the design space. The master observes that variation as it
    solves boxes, so the upper bound of the sweep needs no user at all once a
    couple of boxes are in the database. What it needs instead is the headroom
    of :data:`.HEADROOM`, the spread over the boxes solved being a lower estimate
    of the spread over the design space.

    Args:
        values: The objective values of the boxes already solved.

    Returns:
        The spread of the finite values among them, or ``0.0`` when fewer than
        two of them are finite, which is not yet a scale.
    """
    finite = [float(value) for value in values if isfinite(value)]
    if len(finite) < 2:
        return 0.0

    return max(finite) - min(finite)


@dataclass(frozen=True)
class Deployment:
    """One probe of a sweep that proposed a box not yet solved."""

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


@dataclass(frozen=True)
class ConvexitySweep:
    """A ladder of convexity values, and the rule redeploying its probes.

    The sweep is a policy and not an optimizer: :meth:`.deploy` is given the
    function that solves the master at one value of the convexity setting, and
    decides which values to give it.
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
        cls,
        max_value: float,
        n_points: int = N_CONVEXITY_POINTS,
        decades: float = LADDER_DECADES,
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
            index: The index of the probe, from zero.

        Returns:
            The rungs, the probe's own first.

        Raises:
            IndexError: When the probe is not on the ladder.
        """
        if not 0 <= index < self.n_points:
            msg = f"The probe index must be in [0, {self.n_points}); got {index}."
            raise IndexError(msg)

        return self.ladder[index:]

    def deploy(self, solve: Callable[[float], Any | None]) -> tuple[Deployment, ...]:
        """Deploy one iteration of the sweep.

        Every probe is given its own rung, and redeployed one rung up whenever
        the master proposes nothing new there, until it proposes a box that has
        not been solved or the ladder is exhausted.

        Args:
            solve: The function solving the master at one value of the convexity
                setting, returning what it proposes, or ``None`` when it
                proposes nothing new. The proposal has to be hashable, so that
                two probes landing on the same box count once.

        Returns:
            The deployments that proposed a box, in the order of the probes. An
            empty result is the stopping criterion of the sweep: no value up to
            the upper bound proposes a box that has not been solved.
        """
        deployments = []
        proposed = set()
        for index in range(self.n_points):
            starting_value = self.ladder[index]
            for value in self.rungs(index):
                proposal = solve(value)
                if proposal is None or proposal in proposed:
                    continue

                proposed.add(proposal)
                deployments.append(
                    Deployment(
                        index=index,
                        value=value,
                        proposal=proposal,
                        starting_value=starting_value,
                    )
                )
                break

        return tuple(deployments)


@dataclass
class ConvexitySweepSettings:
    """What the sweep asks of the user, in place of a value to calibrate.

    Two numbers, neither of which is the quantity the criticism is about:

    ``max_value``
        the **upper bound** of the sweep. ``None``, the default, takes it from
        the spread of the objective over the boxes already solved, with the
        headroom that spread needs, which makes the run ask for nothing at all.
        A bound erring high keeps the low rungs on the ladder, so it costs probes
        rather than quality.

    ``n_points``
        the number of rungs, hence of probes per iteration. One recovers the
        single value the master takes today.
    """

    max_value: float | None = None
    """The upper bound of the sweep, or ``None`` to read it off the objective."""

    n_points: int = N_CONVEXITY_POINTS
    """The number of rungs of the ladder."""

    decades: float = LADDER_DECADES
    """The number of decades the ladder spans below its upper bound."""

    headroom: float = HEADROOM
    """The factor applied to an upper bound read off the objective."""

    def __post_init__(self) -> None:
        """Check the settings.

        Raises:
            ValueError: When the upper bound is not positive, when the number of
                rungs is not positive, or when the headroom is not positive.
        """
        if self.max_value is not None and self.max_value <= 0.0:
            msg = (
                f"The upper bound of the sweep must be positive; got {self.max_value}."
            )
            raise ValueError(msg)

        if self.n_points < 1:
            msg = f"The number of rungs must be positive; got {self.n_points}."
            raise ValueError(msg)

        if self.headroom <= 0.0:
            msg = f"The headroom must be positive; got {self.headroom}."
            raise ValueError(msg)

    def create_sweep(self, observed_scale: float = 0.0) -> ConvexitySweep | None:
        """Return the sweep these settings describe.

        Args:
            observed_scale: The variation of the objective over the boxes
                already solved, which the headroom lifts into the upper bound
                when :attr:`.max_value` is ``None``. See
                :func:`.objective_scale`.

        Returns:
            The sweep, or ``None`` when the upper bound is neither given nor
            observed yet, which is the first iterations of a run.
        """
        if self.max_value is not None:
            max_value = self.max_value
        else:
            max_value = observed_scale * self.headroom

        if max_value <= 0.0:
            return None

        return ConvexitySweep.from_bounds(max_value, self.n_points, self.decades)
