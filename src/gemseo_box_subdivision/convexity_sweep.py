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
r"""Asking the master to sweep the convexity, rather than calibrating a value.

The convexity margin ``min_dfk`` and the convexification constant are absolute
quantities in the units of the objective, and annex C says neither transfers
between problems: a margin of :math:`100` reaches the optimum from every starting
point on Rastrigin, which spans about eighty, and is the worst of those tried on
Ackley, which spans about twenty-two. Asking the user for a number calibrated
against a quantity they do not know is the standing criticism of the method.

The answer is to stop choosing. The master already probes one trust-region radius
per parallel point, over ``geomspace(step / 2, step)``: the parallel points are a
sweep and not a batch. The same probes can carry a **ladder** of convexity
values, the low rungs proposing the box next door and the high rungs the box
across the design space, with every probe that proposes nothing new redeployed a
rung higher. The user then supplies an upper bound and a number of points, or
nothing at all.

**That loop belongs to the master, and it is implemented there**, in
``gemseo_bilevel_outer_approximation.algos.opt.core.convexity_sweep`` and the
probe loop beside it, under the settings ``convexity_sweep_points`` and
``convexity_sweep_max``. What this module holds is what is this package's own:

- :class:`.ConvexitySweepSettings`, the two numbers a run of this package asks
  for, which :meth:`.BoxSubdivisionSettings.to_master_settings` turns into those
  two settings of the master;
- the ladder itself, **re-exported** from the master, so that the rest of the
  package has one name for it wherever it lives.

:data:`.MASTER_SWEEPS_CONVEXITY` says which master is installed. Against one that
predates the sweep, the settings above are not accepted and the ladder is not
there to import: the package then falls back to
``_convexity_sweep_fallback`` and to the stub of
``benchmarks/convexity_sweep.py``, which drives the released master from
outside. Both are temporary, and both go when the master ships the sweep.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from gemseo_bilevel_outer_approximation.algos.opt.core.convexity_sweep import (
        HEADROOM,
    )
    from gemseo_bilevel_outer_approximation.algos.opt.core.convexity_sweep import (
        LADDER_DECADES,
    )
    from gemseo_bilevel_outer_approximation.algos.opt.core.convexity_sweep import (
        ConvexitySweep,
    )
    from gemseo_bilevel_outer_approximation.algos.opt.core.convexity_sweep import (
        convexity_ladder,
    )
    from gemseo_bilevel_outer_approximation.algos.opt.core.convexity_sweep import (
        objective_scale,
    )

    MASTER_SWEEPS_CONVEXITY = True
    """Whether the installed master sweeps the convexity on its own."""
except ImportError:  # pragma: no cover - depends on the master installed
    from gemseo_box_subdivision._convexity_sweep_fallback import HEADROOM
    from gemseo_box_subdivision._convexity_sweep_fallback import LADDER_DECADES
    from gemseo_box_subdivision._convexity_sweep_fallback import ConvexitySweep
    from gemseo_box_subdivision._convexity_sweep_fallback import convexity_ladder
    from gemseo_box_subdivision._convexity_sweep_fallback import objective_scale

    MASTER_SWEEPS_CONVEXITY = False
    """Whether the installed master sweeps the convexity on its own."""

N_CONVEXITY_POINTS: int = 4
"""The default number of rungs of the ladder.

The same count as the parallel points of the master, so that a probe per rung
costs what the parallel probing already costs.
"""

__all__ = [
    "HEADROOM",
    "LADDER_DECADES",
    "MASTER_SWEEPS_CONVEXITY",
    "N_CONVEXITY_POINTS",
    "ConvexitySweep",
    "ConvexitySweepSettings",
    "convexity_ladder",
    "objective_scale",
]


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
        single value the master takes without a sweep.

    The span of the ladder and the headroom of an observed bound are **not**
    settings: they are constants of the master, ``LADDER_DECADES`` and
    ``HEADROOM``, one dimensionless and one a count of decades, neither in
    the units of anybody's objective.
    """

    max_value: float | None = None
    """The upper bound of the sweep, or ``None`` to read it off the objective."""

    n_points: int = N_CONVEXITY_POINTS
    """The number of rungs of the ladder."""

    def __post_init__(self) -> None:
        """Check the settings.

        Raises:
            ValueError: When the upper bound is not positive, or when the number
                of rungs is not positive.
        """
        if self.max_value is not None and self.max_value <= 0.0:
            msg = (
                f"The upper bound of the sweep must be positive; got {self.max_value}."
            )
            raise ValueError(msg)

        if self.n_points < 1:
            msg = f"The number of rungs must be positive; got {self.n_points}."
            raise ValueError(msg)

    def create_sweep(self, observed_scale: float = 0.0) -> ConvexitySweep | None:
        """Return the ladder these settings describe.

        The master builds this for itself, from the objective values it has;
        this is the same ladder, for a caller that has none of them, such as
        :meth:`.BoxSubdivisionSettings.to_master_settings` deciding what a
        master without a sweep should be given instead.

        Args:
            observed_scale: The variation of the objective over the boxes
                already solved, which the headroom lifts into the upper bound
                when :attr:`.max_value` is ``None``. See
                :func:`.objective_scale`.

        Returns:
            The ladder, or ``None`` when the upper bound is neither given nor
            observed yet, which is the first iterations of a run.
        """
        max_value = (
            self.max_value if self.max_value is not None else observed_scale * HEADROOM
        )
        if max_value <= 0.0:
            return None

        return ConvexitySweep.from_bounds(max_value, self.n_points)

    def to_master_settings(self) -> dict[str, float | int]:
        """Return the settings asking the master for this sweep.

        Returns:
            The settings of the master, empty when the installed master does not
            sweep the convexity, since it would reject them.
        """
        if not MASTER_SWEEPS_CONVEXITY:
            return {}

        return {
            "convexity_sweep_points": self.n_points,
            # The master reads a bound of zero off the objective, which is what
            # an upper bound left unset asks it to do.
            "convexity_sweep_max": self.max_value or 0.0,
        }
