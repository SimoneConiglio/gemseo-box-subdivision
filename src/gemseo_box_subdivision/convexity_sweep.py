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

- the translation of what a run asks for into those two settings of the master,
  which :meth:`.SweptBoxSubdivisionSettings.to_master_settings` does: the upper
  bound as it is given, and the rungs from the parallel points;
- the ladder itself, **re-exported** from the master, so that the rest of the
  package has one name for it wherever it lives.

:data:`.MASTER_SWEEPS_CONVEXITY` says which master is installed. Against one that
predates the sweep, the settings above are not accepted and the ladder is not
there to import: the package then falls back to its own
:mod:`~gemseo_box_subdivision._convexity_sweep_fallback` copy of the ladder, and
to :mod:`~gemseo_box_subdivision._convexity_sweep_driver`, which sweeps that
ladder around the solves of the released master. Both are temporary, and both go
when the master ships the sweep.
"""

from __future__ import annotations

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

__all__ = [
    "HEADROOM",
    "LADDER_DECADES",
    "MASTER_SWEEPS_CONVEXITY",
    "ConvexitySweep",
    "convexity_ladder",
    "objective_scale",
]
