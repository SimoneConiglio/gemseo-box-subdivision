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
"""The configurations of the master problem, which must not be mixed.

The master has **two distinct mechanisms** for keeping its cuts usable on a
non-convex value function. They rest on different arguments and are not meant to
be combined:

`pure_convexification`
: adds to the objective a convex term vanishing at the integer points, whose
  constant, once it dominates the concavity of the relaxed problem, makes the
  relaxation convex and the outer approximation convergent. It is driven by
  ``convexification_constant`` alone, with ``adapt`` off.

`adaptive`
: repairs the slope of each cut by least squares against the pairs of points
  already observed, so that no cut over-predicts a value that has been measured,
  with ``min_dfk`` as the convexity margin. It is driven by ``adapt`` and
  ``min_dfk``, with no convexification constant.

Measuring the two together, as an earlier version of these benchmarks did,
measures neither.
"""

from __future__ import annotations

from types import MappingProxyType

ADAPTIVE = MappingProxyType({
    "adapt": True,
    "min_dfk": 100.0,
    "convexification_constant": 0.0,
    "number_of_parallel_points": 4,
})
"""The adaptive repair of the cut slopes, which reaches the optimum most often.

Two of its settings are essential rather than an optimization.

Several **parallel points**: the master probes one trust-region radius per point,
over ``geomspace(step / 2, step)``, so that a feasible master problem stays
available. With a single point the run stops after two or three boxes, whatever
the convexity margin.

A convexity margin on the **scale of the objective**: ``min_dfk`` is subtracted
from an objective difference, so it is an absolute quantity in the units of the
objective, not a ratio, and it has to be scaled to the problem. On the Rastrigin
benchmark, whose objective spans about eighty, the margin crosses a threshold and
then **saturates** rather than passing through a window: at two variables and
four parallel points it reaches the optimum from two starting points out of
twenty at $1$, ten at $10$, and nineteen or twenty from $30$ upwards; at five
variables and ten subdivisions, from none at $10$, two out of three at $30$ and
all three at $100$ and at $300$ in an earlier study with three starting
points. What an over-large margin costs is sub-problems, not quality, so
the default sits at the first value that saturates.
"""

PURE_CONVEXIFICATION = MappingProxyType({
    "adapt": False,
    "min_dfk": 0.0,
    "convexification_constant": 100.0,
    "number_of_parallel_points": 1,
})
"""The convex term added to the objective.

The constant has to dominate the concavity of the relaxed problem and no more.
It is an absolute quantity, of the order of the variation of the objective over
the design space, about eighty on the Rastrigin benchmark, and unlike the
convexity margin of the adaptive repair it passes through a genuine **window**:
too small and the cuts stay invalid, too large and every unexplored box outranks
the incumbent whatever the cuts say, so the master ranks them by nothing in
particular.

The window narrows as the dimension grows. At two variables and ten
subdivisions, constants of $30$ to $200$ reach the optimum from twelve to
eighteen starting points out of twenty. At five variables none of the constants
tried reaches it from more than five starting points out of twenty, $50$ being
the best, against fifteen for the adaptive repair with four parallel points.

An exaggerated constant is therefore not a conservative choice, and the regime
where the convergence argument would apply is out of reach anyway, the run ending
on the trust region or on the stall counter rather than on its optimality test.
This mechanism is kept for the argument it rests on rather than as a default;
see `tune_convexification.py`.
"""

CONFIGURATIONS = MappingProxyType({
    "adaptive": ADAPTIVE,
    "pure_convexification": PURE_CONVEXIFICATION,
})
"""The configurations of the master, by name."""

CONFIGURATION_NAMES = tuple(CONFIGURATIONS)
"""The names of the configurations of the master."""

DEFAULT_CONFIGURATION = "adaptive"
"""The configuration reaching the optimum with the fewest boxes."""

TRUST_REGION_RADIUS = 2
"""The radius of the trust region of the master, in components changed.

The master restricts each iteration to a neighbourhood of the incumbent box, and
the distance it measures is the number of components a candidate changes, every
subdivision being weighed alike by the design spaces of this package.

A radius of two is a compromise over the benchmark problems, far from the
radius at which the region stops constraining,
:attr:`.BoxSubdivision.max_step`. On Rastrigin with five variables and ten
subdivisions, from twenty starting points, a radius of one reaches the optimum
from seven, and radii of two, three and five from fifteen, at median costs of
$1757$, $2049$ and $2500$ evaluations. On Styblinski-Tang, radii of three and
five reach it from all twenty starting points and a radius of two from fifteen.

In two variables, a radius of one reaches the optimum of Rastrigin from every
starting point for a median of $458$ evaluations, against $845$ with no region
at all.
"""
