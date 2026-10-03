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

"""The box-subdivision method on the GGP short cantilever, a real application.

The problem is the Short Cantilever 2D of the `generalized_geometry_projection
<https://github.com/SimoneConiglio/generalized_geometry_projection>`_ package:
108 variables, the pose, length, thickness and density of 18 bars, a compliance
to minimize under a volume constraint, and adjoint gradients. The scripts here
drive that package's ``benchmarks/sc2d_box_subdivision.py``, from its branch
``claude/gemseo-mox-cantilever-optimization-dl9ejh``, and have to be run from
that repository in its environment, which needs legacy FEniCS 2019.1 from
conda-forge. None of this runs in the test suite.

``trivial_start.py``
    the box-subdivision and MMA runs from a trivial start: the preset's bar
    poses, the length, the thickness and the density at mid-range.
``global_baselines.py``
    DIRECT, CMA-ES, EGO and a multistart of MMA from the same start, each
    solve logged so that a run cut short resumes.
``record_box.py``
    the box-subdivision run again, keeping every design, for the animation.
``cantilever_gif.py``
    the animation of that run.
``parallel_multistart.py``
    a multistart of MMA, its starts distributed over processes.
``cantilever_parallel_gif.py``
    the animation of a run whose probes are solved in parallel, recorded by
    ``trivial_start.py --record``, round by round: the one the documentation
    shows, with nine probes.
"""
