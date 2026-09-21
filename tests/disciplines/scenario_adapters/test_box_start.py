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
"""Tests for the scenario adapter starting the sub-problem inside its box."""

from __future__ import annotations

import pytest
from gemseo import create_scenario
from gemseo.algos.design_space import DesignSpace
from gemseo.core.discipline import Discipline
from gemseo.settings.formulations import DisciplinaryOpt_Settings
from gemseo.settings.opt import SLSQP_Settings
from numpy import array
from numpy import concatenate
from numpy import cos
from numpy import sin
from numpy import zeros

from gemseo_box_subdivision.design_spaces import create_box_design_space
from gemseo_box_subdivision.disciplines.box_constraint import BoxConstraint
from gemseo_box_subdivision.disciplines.scenario_adapters.box_start import (
    create_box_start_adapter_class,
)
from gemseo_box_subdivision.subdivisions.box import BoxSubdivision

N_SUBDIVISIONS = 4


class Multimodal(Discipline):
    """A multimodal objective with one local minimum per box."""

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


def _create_scenario(initial_value: float, box_start: bool):
    """Create the bi-level scenario, with or without the box-start adapter.

    Args:
        initial_value: The initial value of the design variable.
        box_start: Whether to start each sub-problem at the center of its box.

    Returns:
        The scenario and the subdivision.
    """
    design_space = DesignSpace()
    design_space.add_variable(
        "x", lower_bound=0.0, upper_bound=1.0, value=initial_value
    )
    subdivision = BoxSubdivision.from_design_space(design_space, N_SUBDIVISIONS)
    settings = {}
    if box_start:
        settings["scenario_adapter_cls"] = create_box_start_adapter_class(subdivision)

    scenario = create_scenario(
        [Multimodal(), BoxConstraint(subdivision)],
        "f",
        create_box_design_space(subdivision, design_space),
        formulation_name="Benders",
        main_problem_design_variables=["x_box"],
        sub_problem_algo_settings=SLSQP_Settings(max_iter=50),
        sub_problem_formulation_settings=DisciplinaryOpt_Settings(),
        **settings,
    )
    scenario.formulation.add_constraint(BoxConstraint.DEFAULT_OUTPUT_NAME)
    return scenario, subdivision


def _evaluate_box(scenario, index: int) -> float:
    """Solve the sub-problem of one box.

    Args:
        scenario: The bi-level scenario.
        index: The index of the box.

    Returns:
        The optimum of the sub-problem.
    """
    one_hot = zeros(N_SUBDIVISIONS)
    one_hot[index] = 1.0
    problem = scenario.formulation.optimization_problem
    return float(problem.objective.evaluate(one_hot).ravel()[0])


@pytest.mark.parametrize("index", range(N_SUBDIVISIONS))
def test_each_box_reaches_its_own_optimum(index) -> None:
    """Check that every box is solved from a point inside itself.

    The initial value lies in the last box, so without the adapter the
    sub-problems of the other boxes start outside of their own box.
    """
    scenario, subdivision = _create_scenario(0.95, box_start=True)
    value = _evaluate_box(scenario, index)
    # Solving a box from its center cannot do worse than the value at its center.
    lower_bound = subdivision.get_lower_bounds("x")[0, index]
    upper_bound = subdivision.get_upper_bounds("x")[0, index]
    center = (lower_bound + upper_bound) / 2.0
    assert value <= sin(6.0 * center) + 0.3 * (center - 0.4) ** 2 + 1e-6


def test_box_start_improves_the_enumeration() -> None:
    """Check that starting inside the box finds the global optimum by enumeration.

    Starting every sub-problem from the same initial value, as GEMSEO does by
    default, makes most of them start outside of their own box, and the
    enumeration of the boxes then misses the global optimum.
    """
    with_adapter, _ = _create_scenario(0.05, box_start=True)
    best_with = min(_evaluate_box(with_adapter, i) for i in range(N_SUBDIVISIONS))
    # The global optimum of the problem on [0, 1].
    assert best_with == pytest.approx(-0.956171, abs=1e-4)


def test_adapter_class_is_a_benders_adapter() -> None:
    """Check that the returned class can be used by the Benders formulation."""
    design_space = DesignSpace()
    design_space.add_variable("x", lower_bound=0.0, upper_bound=1.0, value=0.5)
    subdivision = BoxSubdivision.from_design_space(design_space, N_SUBDIVISIONS)
    from gemseo_bilevel_outer_approximation.disciplines.scenario_adapters.mdo_scenario_adapter_benders import (  # noqa: E501
        MDOScenarioAdapterBenders,
    )

    adapter_class = create_box_start_adapter_class(subdivision)
    assert issubclass(adapter_class, MDOScenarioAdapterBenders)


def test_subdivided_variable_outside_the_sub_problem() -> None:
    """Check that a subdivided variable of the main problem is skipped.

    The adapter only sets the starting point of the variables that the
    sub-problem actually solves for, so a subdivided variable kept in the main
    problem must be left alone rather than raise.
    """
    design_space = DesignSpace()
    design_space.add_variable("x", lower_bound=0.0, upper_bound=1.0, value=0.5)
    design_space.add_variable("y", lower_bound=0.0, upper_bound=1.0, value=0.5)
    subdivision = BoxSubdivision.from_design_space(design_space, N_SUBDIVISIONS, ["x"])
    adapter_class = create_box_start_adapter_class(subdivision)
    scenario = create_scenario(
        [Sum(), BoxConstraint(subdivision)],
        "s",
        create_box_design_space(subdivision, design_space),
        formulation_name="Benders",
        # x is kept in the main problem, so the sub-problem only solves for y.
        main_problem_design_variables=["x_box", "x"],
        sub_problem_algo_settings=SLSQP_Settings(max_iter=10),
        sub_problem_formulation_settings=DisciplinaryOpt_Settings(),
        scenario_adapter_cls=adapter_class,
    )
    sub_design_space = scenario.formulation.sub_problem_design_space
    assert "x" not in sub_design_space
    one_hot = zeros(N_SUBDIVISIONS)
    one_hot[0] = 1.0
    value = scenario.formulation.optimization_problem.objective.evaluate(
        concatenate([one_hot, array([0.1])])
    )
    assert value is not None


def test_sub_problem_keeps_the_variables_that_are_not_subdivided() -> None:
    """Check that a sub-problem mixing subdivided and whole variables runs.

    Subdividing some of the variables only leaves the others as ordinary
    variables of the sub-problem, so the starting point the adapter sets covers
    part of the sub-problem design space; the rest keeps the value it has.
    """
    design_space = DesignSpace()
    design_space.add_variable("x", lower_bound=0.0, upper_bound=1.0, value=0.5)
    design_space.add_variable("y", lower_bound=0.0, upper_bound=1.0, value=0.25)
    subdivision = BoxSubdivision.from_design_space(design_space, N_SUBDIVISIONS, ["x"])
    scenario = create_scenario(
        [Sum(), BoxConstraint(subdivision)],
        "s",
        create_box_design_space(subdivision, design_space),
        formulation_name="Benders",
        # Only the box is decided by the main problem: the sub-problem solves
        # for the subdivided x *and* for the whole y.
        main_problem_design_variables=["x_box"],
        sub_problem_algo_settings=SLSQP_Settings(max_iter=10),
        sub_problem_formulation_settings=DisciplinaryOpt_Settings(),
        scenario_adapter_cls=create_box_start_adapter_class(subdivision),
    )
    scenario.formulation.add_constraint(BoxConstraint.DEFAULT_OUTPUT_NAME)
    sub_design_space = scenario.formulation.sub_problem_design_space
    assert set(sub_design_space) == {"x", "y"}

    index = 2
    one_hot = zeros(N_SUBDIVISIONS)
    one_hot[index] = 1.0
    value = float(
        scenario.formulation.optimization_problem.objective.evaluate(one_hot).ravel()[0]
    )
    # The minimum of x + y over the box of x and the whole range of y.
    assert value == pytest.approx(subdivision.get_lower_bounds("x")[0, index], abs=1e-6)


class Sum(Discipline):
    """A discipline summing two scalar variables."""

    def __init__(self) -> None:  # noqa: D107
        super().__init__()
        self.io.input_grammar.update_from_data({"x": array([0.5]), "y": array([0.5])})
        self.io.output_grammar.update_from_data({"s": array([0.0])})
        self.default_input_data = {"x": array([0.5]), "y": array([0.5])}

    def _run(self, input_data):  # noqa: ANN001, ANN202
        return {"s": input_data["x"] + input_data["y"]}

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        self.jac["s"]["x"] = array([[1.0]])
        self.jac["s"]["y"] = array([[1.0]])
