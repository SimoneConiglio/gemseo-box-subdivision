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
"""Integration test of the box-subdivision outer approximation.

The pieces of the package are assembled into a bi-level scenario and run on a
multimodal problem, to check that the main problem explores the boxes while the
sub-problem exploits each of them.
"""

from __future__ import annotations

import pytest
from gemseo import create_scenario
from gemseo.algos.design_space import DesignSpace
from gemseo.core.discipline import Discipline
from gemseo.settings.formulations import DisciplinaryOpt_Settings
from gemseo.settings.opt import SLSQP_Settings
from gemseo_bilevel_outer_approximation.algos.opt.bilevel_master_outer_approximation.bilevel_master_outer_approximation_settings import (  # noqa: E501
    BILEVEL_MASTER_OUTER_APPROXIMATION_Settings,
)
from numpy import array
from numpy import cos
from numpy import sin

from gemseo_box_subdivision.design_spaces import create_box_design_space
from gemseo_box_subdivision.disciplines.box_constraint import BoxConstraint
from gemseo_box_subdivision.subdivisions.box import BoxSubdivision

N_SUBDIVISIONS = 4
"""The number of boxes of the subdivision."""

X_OPT = 0.779078
"""The global minimizer of the objective on [0, 1]."""

F_OPT = -0.956171
"""The global minimum of the objective on [0, 1]."""


class Multimodal(Discipline):
    """A multimodal objective with a local minimum near x = 0 and a global one."""

    def __init__(self) -> None:  # noqa: D107
        super().__init__()
        self.io.input_grammar.update_from_data({"x": array([0.5])})
        self.io.output_grammar.update_from_data({"f": array([0.0])})
        self.default_input_data = {"x": array([0.5])}

    def _run(self, input_data):  # noqa: ANN001, ANN202
        x = input_data["x"][0]
        return {"f": array([sin(6.0 * x) + 0.3 * (x - 0.4) ** 2])}

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        x = self.io.data["x"][0]
        self.jac["f"]["x"] = array([[6.0 * cos(6.0 * x) + 0.6 * (x - 0.4)]])


def _create_scenario(initial_value: float):
    """Create the bi-level scenario of the box-subdivided problem.

    Args:
        initial_value: The initial value of the design variable.

    Returns:
        The scenario and the subdivision.
    """
    design_space = DesignSpace()
    design_space.add_variable(
        "x", lower_bound=0.0, upper_bound=1.0, value=initial_value
    )
    subdivision = BoxSubdivision.from_design_space(design_space, N_SUBDIVISIONS)
    scenario = create_scenario(
        [Multimodal(), BoxConstraint(subdivision)],
        "f",
        create_box_design_space(subdivision, design_space),
        formulation_name="Benders",
        main_problem_design_variables=["x_box"],
        sub_problem_algo_settings=SLSQP_Settings(max_iter=50),
        sub_problem_formulation_settings=DisciplinaryOpt_Settings(),
    )
    scenario.formulation.add_constraint(BoxConstraint.DEFAULT_OUTPUT_NAME)
    return scenario, subdivision


@pytest.mark.parametrize("initial_value", [0.1, 0.5, 0.9])
def test_global_optimum_is_found(initial_value) -> None:
    """Check that the global optimum is found whatever the starting box.

    Starting from 0.1 puts the initial point in the basin of a local minimum,
    which a local solver alone would not escape.
    """
    scenario, _ = _create_scenario(initial_value)
    scenario.execute(BILEVEL_MASTER_OUTER_APPROXIMATION_Settings(max_iter=12))
    result = scenario.optimization_result
    assert result.f_opt == pytest.approx(F_OPT, abs=1e-4)
    # The last box is the one containing the global minimizer.
    assert list(result.x_opt) == [0.0, 0.0, 0.0, 1.0]


def test_fewer_sub_problems_than_boxes() -> None:
    """Check that the main problem does not enumerate the boxes.

    This is the property the method has to exhibit: the outer-approximation cuts
    must drive the exploration towards the global optimum without solving the
    sub-problem of every box.
    """
    scenario, subdivision = _create_scenario(0.1)
    scenario.execute(BILEVEL_MASTER_OUTER_APPROXIMATION_Settings(max_iter=12))
    n_sub_problems = len(scenario.formulation.optimization_problem.database)
    assert n_sub_problems < subdivision.n_boxes


def test_sub_problem_optimum_is_in_the_selected_box() -> None:
    """Check that the sub-problem optimum lies in the box chosen by the main one."""
    scenario, subdivision = _create_scenario(0.1)
    scenario.execute(BILEVEL_MASTER_OUTER_APPROXIMATION_Settings(max_iter=12))
    index = list(scenario.optimization_result.x_opt).index(1.0)
    lower_bound = subdivision.get_lower_bounds("x")[0, index]
    upper_bound = subdivision.get_upper_bounds("x")[0, index]
    assert lower_bound <= X_OPT <= upper_bound
