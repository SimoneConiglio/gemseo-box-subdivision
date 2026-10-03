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
"""Tests for the refusal of a constraint the adapter cannot linearize."""

from __future__ import annotations

import re

import pytest
from gemseo.algos.design_space import DesignSpace
from gemseo.core.discipline import Discipline
from gemseo.disciplines.linear_combination import LinearCombination
from numpy import array
from numpy import zeros

from gemseo_box_subdivision import BoxConstraint
from gemseo_box_subdivision import BoxSubdivisionScenario
from gemseo_box_subdivision import BoxSubdivisionSettings
from gemseo_box_subdivision import find_renamed_constraints

N_SUBDIVISIONS = 3


class Quad(Discipline):
    """f = (x - 3)^2, g = x - 2."""

    def __init__(self) -> None:
        super().__init__()
        self.io.input_grammar.update_from_data({"x": zeros(1)})
        self.io.output_grammar.update_from_data({"f": zeros(1), "g": zeros(1)})
        self.default_input_data = {"x": zeros(1)}

    def _run(self, input_data):  # noqa: ANN001, ANN202
        x = input_data["x"]
        return {"f": (x - 3.0) ** 2, "g": x - 2.0}

    def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ANN001
        self._init_jacobian(input_names, output_names)
        x = self.io.data["x"]
        self.jac["f"]["x"] = array([[2.0 * (x[0] - 3.0)]])
        self.jac["g"]["x"] = array([[1.0]])


def design_space() -> DesignSpace:
    """Return the design space of the quadratic."""
    space = DesignSpace()
    space.add_variable("x", lower_bound=0.0, upper_bound=6.0, value=1.0)
    return space


def scenario(disciplines=None) -> BoxSubdivisionScenario:  # noqa: ANN001
    """Return a scenario over the quadratic, cheap enough to execute."""
    return BoxSubdivisionScenario(
        disciplines or [Quad()],
        "f",
        design_space(),
        n_subdivisions=N_SUBDIVISIONS,
        settings=BoxSubdivisionSettings(
            convexity_margin=10.0, max_iter=4, sub_problem_max_iter=5
        ),
    )


def sub_problem_problem(a_scenario):  # noqa: ANN001, ANN201
    """Return the optimization problem of the sub-problem of a scenario."""
    adapter = a_scenario.formulation.sub_problem_scenario_adapter
    return adapter.scenario.formulation.optimization_problem


def sub_problem_constraints(a_scenario) -> list[str]:  # noqa: ANN001
    """Return the names of the constraints of the sub-problem."""
    return list(sub_problem_problem(a_scenario).constraints.get_names())


def test_a_constraint_named_after_its_output_is_accepted() -> None:
    """Check that the ordinary case is untouched."""
    a_scenario = scenario()
    a_scenario.formulation.add_constraint("g", constraint_type="ineq", main_level=True)
    assert sub_problem_constraints(a_scenario) == ["g"]
    a_scenario.execute()


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"constraint_name": "g_upper"}, "g_upper"),
        ({"positive": True}, "-g"),
        ({"value": 0.5}, "[g-0.5]"),
    ],
)
def test_a_renamed_constraint_is_refused_where_it_is_written(kwargs, expected) -> None:  # noqa: ANN001
    """Check the three ways of renaming a constraint, each refused at once.

    Each of them used to raise ``KeyError`` from the Jacobian of the adapter,
    the first time the master linearized it, which a short run never reaches.
    """
    a_scenario = scenario()
    message = re.escape(f"{expected!r}, built from ['g']")
    with pytest.raises(ValueError, match=message):
        a_scenario.formulation.add_constraint(
            "g", constraint_type="ineq", main_level=True, **kwargs
        )


def test_the_message_names_the_way_around_it() -> None:
    """Check that the refusal says what to write instead."""
    a_scenario = scenario()
    with pytest.raises(ValueError, match="LinearCombination"):
        a_scenario.formulation.add_constraint(
            "g", constraint_type="ineq", constraint_name="g_upper"
        )


def test_a_refused_constraint_is_not_added() -> None:
    """Check that a refusal leaves the sub-problem as it was.

    The constraint is added before being checked, since what makes it unusable
    is the name GEMSEO gives it, so the refusal has to undo that.
    """
    a_scenario = scenario()
    with pytest.raises(ValueError, match="named after no output"):
        a_scenario.formulation.add_constraint(
            "g", constraint_type="ineq", constraint_name="g_upper"
        )

    assert sub_problem_constraints(a_scenario) == []
    # And the scenario still takes an ordinary constraint afterwards.
    a_scenario.formulation.add_constraint("g", constraint_type="ineq")
    assert sub_problem_constraints(a_scenario) == ["g"]


def test_the_band_written_as_two_outputs_runs() -> None:
    """Check the way around the limitation, a discipline output per side.

    ``|g| <= 0.5`` as two inequalities, each named after an output of its own,
    which is what the refusal directs a caller to.
    """
    a_scenario = scenario([
        Quad(),
        LinearCombination(["g"], "g_upper", input_coefficients={"g": 1.0}, offset=-0.5),
        LinearCombination(
            ["g"], "g_lower", input_coefficients={"g": -1.0}, offset=-0.5
        ),
    ])
    for name in ("g_upper", "g_lower"):
        a_scenario.formulation.add_constraint(
            name, constraint_type="ineq", main_level=True
        )

    assert sub_problem_constraints(a_scenario) == ["g_upper", "g_lower"]
    a_scenario.execute()


def test_the_constraint_formulation_keeps_its_own_constraint() -> None:
    """Check that the box constraint the formulation declares is not refused."""
    a_scenario = BoxSubdivisionScenario(
        [Quad()],
        "f",
        design_space(),
        n_subdivisions=N_SUBDIVISIONS,
        formulation="constraint",
        settings=BoxSubdivisionSettings(convexity_margin=10.0, max_iter=4),
    )
    assert sub_problem_constraints(a_scenario) == [BoxConstraint.DEFAULT_OUTPUT_NAME]


def test_the_multi_resolution_encoding_is_guarded_too() -> None:
    """Check that the third construction refuses a renamed constraint as well."""
    a_scenario = BoxSubdivisionScenario(
        [Quad()],
        "f",
        design_space(),
        n_subdivisions=2,
        levels=2,
        settings=BoxSubdivisionSettings(convexity_margin=10.0, max_iter=4),
    )
    with pytest.raises(ValueError, match="named after no output"):
        a_scenario.formulation.add_constraint(
            "g", constraint_type="ineq", positive=True
        )


def test_find_renamed_constraints_reads_the_problem() -> None:
    """Check the reader the refusal is built on, against a problem of its own."""
    a_scenario = scenario()
    problem = sub_problem_problem(a_scenario)
    assert find_renamed_constraints(problem) == ()

    a_scenario.formulation.add_constraint("g", constraint_type="ineq")
    assert find_renamed_constraints(problem) == ()
