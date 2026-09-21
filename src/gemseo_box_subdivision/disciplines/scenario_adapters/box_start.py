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
"""A scenario adapter starting the sub-problem inside its box."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

from gemseo_bilevel_outer_approximation.disciplines.scenario_adapters.mdo_scenario_adapter_benders import (  # noqa: E501
    MDOScenarioAdapterBenders,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gemseo_box_subdivision.subdivisions.box import BoxSubdivision


def create_box_start_adapter_class(
    subdivision: BoxSubdivision,
    one_hot_names: Mapping[str, str] = MappingProxyType({}),
) -> type[MDOScenarioAdapterBenders]:
    """Return a scenario adapter starting the sub-problem at the center of its box.

    The sub-problem of a box is solved by a local algorithm, hence its starting
    point decides which local minimum of the box it converges to.

    The adapters of GEMSEO offer two policies, neither of which suits a box
    subdivision: ``reset_x0_before_opt`` restarts every sub-problem from the
    initial value of the design space, which lies outside of all the boxes but
    one, so that most sub-problems start infeasible; and warm-starting from the
    previous sub-problem makes the result depend on the order in which the boxes
    are visited. Setting the starting point from the adapter inputs is not an
    option either, since the main problem only decides the box, not the design
    variables.

    The adapter returned here starts each sub-problem at the center of the box
    selected by the main problem, which is feasible by construction and
    independent of the order of the boxes.

    Args:
        subdivision: The Cartesian subdivision of the design space.
        one_hot_names: The name of the one-hot variable of each subdivided
            variable. If empty, suffix the design variable names with
            :attr:`.BoxSubdivision.ONE_HOT_SUFFIX`.

    Returns:
        The scenario adapter class, to be passed to the ``Benders`` formulation
        through its ``scenario_adapter_cls`` setting.
    """
    names = subdivision.get_one_hot_names(one_hot_names)

    class BoxStartScenarioAdapter(MDOScenarioAdapterBenders):
        """A Benders scenario adapter starting at the center of the box."""

        def _pre_run(self) -> None:
            super()._pre_run()
            design_space = self.scenario.formulation.optimization_problem.design_space
            data = self.io.data
            for variable_name, one_hot_name in names.items():
                if variable_name not in design_space or one_hot_name not in data:
                    continue

                lower_bound, upper_bound = subdivision.compute_bounds(
                    variable_name, data[one_hot_name]
                )
                # One variable at a time: a design space holding variables that
                # are not subdivided rejects a current value covering only some
                # of its variables, and those others keep the value they have.
                design_space.set_current_variable(
                    variable_name, (lower_bound + upper_bound) / 2.0
                )

    return BoxStartScenarioAdapter
