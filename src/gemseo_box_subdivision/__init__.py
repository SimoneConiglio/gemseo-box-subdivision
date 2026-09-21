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
"""A GEMSEO plugin solving multimodal problems by subdividing the design space.

The design space is cut into a Cartesian grid of boxes, which turns the choice of
a region into a categorical variable: a mixed-integer master decides which box to
look into from the cuts of the boxes already solved, and a local solver does the
rest inside it.

One entry point covers every shape of run:

.. code-block:: python

    from gemseo_box_subdivision import BoxSubdivisionScenario

    scenario = BoxSubdivisionScenario(
        [objective_discipline], "f", design_space, n_subdivisions=10
    )
    scenario.execute()

The settings that decide whether a run works are the density of the subdivision
and the convexity margin, which is in the units of the objective. Everything else
the entry point owns. The margin need not be chosen at all: see
:mod:`~gemseo_box_subdivision.convexity_sweep`, which sweeps a ladder of values
across the parallel probes the master already runs.
"""

from __future__ import annotations

from gemseo_box_subdivision.constraints import RENAMING_SHAPES
from gemseo_box_subdivision.constraints import check_constraint_names
from gemseo_box_subdivision.constraints import find_renamed_constraints
from gemseo_box_subdivision.constraints import guard_renamed_constraints
from gemseo_box_subdivision.convexity_sweep import MASTER_SWEEPS_CONVEXITY
from gemseo_box_subdivision.convexity_sweep import ConvexitySweep
from gemseo_box_subdivision.convexity_sweep import convexity_ladder
from gemseo_box_subdivision.convexity_sweep import objective_scale
from gemseo_box_subdivision.design_spaces import create_box_design_space
from gemseo_box_subdivision.design_spaces import create_box_samples
from gemseo_box_subdivision.design_spaces import create_normalized_box_design_space
from gemseo_box_subdivision.disciplines.box_constraint import BoxConstraint
from gemseo_box_subdivision.disciplines.box_mapping import BoxMapping
from gemseo_box_subdivision.disciplines.couplings import keep_couplings_internal
from gemseo_box_subdivision.disciplines.couplings import (
    keep_every_mda_couplings_internal,
)
from gemseo_box_subdivision.disciplines.multi_resolution_mapping import (
    MultiResolutionMapping,
)
from gemseo_box_subdivision.disciplines.scenario_adapters.box_start import (
    create_box_start_adapter_class,
)
from gemseo_box_subdivision.hierarchy import RANKINGS
from gemseo_box_subdivision.hierarchy import SHAPES
from gemseo_box_subdivision.hierarchy import SolvedBox
from gemseo_box_subdivision.hierarchy import compute_cut_model
from gemseo_box_subdivision.hierarchy import read_solved_boxes
from gemseo_box_subdivision.hierarchy import refine_deep
from gemseo_box_subdivision.hierarchy import refine_frontier
from gemseo_box_subdivision.hierarchy import refine_two_levels
from gemseo_box_subdivision.scenario import BoxSubdivisionScenario
from gemseo_box_subdivision.scenario import create_box_subdivision_scenario
from gemseo_box_subdivision.settings import BaseBoxSubdivisionSettings
from gemseo_box_subdivision.settings import BoxSubdivisionSettings
from gemseo_box_subdivision.settings import SweptBoxSubdivisionSettings
from gemseo_box_subdivision.subdivisions.box import BoxSubdivision
from gemseo_box_subdivision.subdivisions.multi_resolution import MultiResolution

__all__ = [
    "MASTER_SWEEPS_CONVEXITY",
    "RANKINGS",
    "RENAMING_SHAPES",
    "SHAPES",
    "BaseBoxSubdivisionSettings",
    "BoxConstraint",
    "BoxMapping",
    "BoxSubdivision",
    "BoxSubdivisionScenario",
    "BoxSubdivisionSettings",
    "ConvexitySweep",
    "MultiResolution",
    "MultiResolutionMapping",
    "SolvedBox",
    "SweptBoxSubdivisionSettings",
    "check_constraint_names",
    "compute_cut_model",
    "convexity_ladder",
    "create_box_design_space",
    "create_box_samples",
    "create_box_start_adapter_class",
    "create_box_subdivision_scenario",
    "create_normalized_box_design_space",
    "find_renamed_constraints",
    "guard_renamed_constraints",
    "keep_couplings_internal",
    "keep_every_mda_couplings_internal",
    "objective_scale",
    "read_solved_boxes",
    "refine_deep",
    "refine_frontier",
    "refine_two_levels",
]
