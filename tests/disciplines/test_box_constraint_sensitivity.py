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
"""Tests for the sensitivity carried by the box constraint.

These tests pin the property the outer-approximation cuts rely on: the
multiplier of the box constraint at a sub-problem optimum is the derivative of
that optimum with respect to the position of the box face.
"""

from __future__ import annotations

from copy import deepcopy

import pytest
from gemseo.core.function.array_function import ArrayFunction
from gemseo.optimization import OptimizationProblem
from gemseo.optimization import SLSQP_Settings
from gemseo.optimization.factory import OptimizationLibraryFactory
from gemseo.optimization.lagrange_multipliers import LagrangeMultipliers
from gemseo.space import DesignSpace
from numpy import array
from numpy import cos
from numpy import sin
from numpy import zeros

from gemseo_box_subdivision.disciplines.box_constraint import BoxConstraint
from gemseo_box_subdivision.subdivisions.box import BoxSubdivision

# A multimodal objective on [0, 1], increasing at x = 0.
OBJECTIVE = lambda x: sin(6.0 * x[0]) + 0.3 * (x[0] - 0.4) ** 2  # noqa: E731
GRADIENT = lambda x: array([6.0 * cos(6.0 * x[0]) + 0.6 * (x[0] - 0.4)])  # noqa: E731

# The objective slope at x = 0, i.e. the exact multiplier of the lower face
# of the first box when the optimum of that box lies on it.
SLOPE_AT_ZERO = 6.0 - 0.6 * 0.4


@pytest.fixture
def design_space() -> DesignSpace:
    """The design space of the original problem."""
    design_space = DesignSpace()
    design_space.add_variable("x", lower_bound=0.0, upper_bound=1.0, value=0.5)
    return design_space


@pytest.fixture
def subdivision(design_space) -> BoxSubdivision:
    """A subdivision of the design space into four boxes."""
    return BoxSubdivision.from_design_space(design_space, 4)


def _solve_box(subdivision, sub_design_space, index):
    """Solve the sub-problem restricted to a box and return its multiplier.

    Args:
        subdivision: The subdivision of the design space.
        sub_design_space: The design space of the sub-problem.
        index: The index of the box.

    Returns:
        The optimal design value and the multiplier of the box constraint.
    """
    discipline = BoxConstraint(subdivision)
    one_hot = zeros(4)
    one_hot[index] = 1.0
    lower_bound = subdivision.get_lower_bounds("x")[0, index]
    upper_bound = subdivision.get_upper_bounds("x")[0, index]

    design_space = deepcopy(sub_design_space)
    design_space.set_current_value({"x": array([(lower_bound + upper_bound) / 2.0])})
    problem = OptimizationProblem(design_space)
    problem.objective = ArrayFunction(OBJECTIVE, "f", jac=GRADIENT)
    problem.add_constraint(
        ArrayFunction(
            lambda x: discipline.execute({"x": x, "x_box": one_hot})["g_box"],
            "g_box",
            f_type=ArrayFunction.ConstraintType.INEQ,
            jac=lambda x: discipline.linearize(
                {"x": x, "x_box": one_hot},
                execute=True,
                compute_all_jacobians=True,
            )["g_box"]["x"],
        )
    )
    OptimizationLibraryFactory().execute(problem, SLSQP_Settings(max_iter=60))
    multipliers = LagrangeMultipliers(problem).compute(problem.solution.x_opt)
    inequality = multipliers.get(LagrangeMultipliers.INEQUALITY)
    multiplier = float(inequality[1][0]) if inequality else 0.0
    return float(problem.solution.x_opt[0]), multiplier


@pytest.mark.parametrize("index", range(4))
def test_sub_problem_stays_in_its_box(design_space, subdivision, index) -> None:
    """Check that the constraint alone confines the sub-problem to its box."""
    x_opt, _ = _solve_box(subdivision, design_space, index)
    assert subdivision.get_lower_bounds("x")[0, index] - 1e-6 <= x_opt
    assert x_opt <= subdivision.get_upper_bounds("x")[0, index] + 1e-6


def test_border_box_multiplier_is_lost_without_a_margin(
    design_space, subdivision
) -> None:
    """Check that a border box loses its multiplier to the design space bound.

    This is the reason why :meth:`.BoxSubdivision.create_relaxed_design_space`
    exists: without a margin the sensitivity of a border box is silently zero.
    """
    x_opt, multiplier = _solve_box(subdivision, design_space, 0)
    assert x_opt == pytest.approx(0.0, abs=1e-6)
    assert multiplier == pytest.approx(0.0, abs=1e-6)


def test_border_box_multiplier_with_a_margin(design_space, subdivision) -> None:
    """Check that a margin restores the multiplier of a border box."""
    relaxed = subdivision.create_relaxed_design_space(design_space)
    x_opt, multiplier = _solve_box(subdivision, relaxed, 0)
    assert x_opt == pytest.approx(0.0, abs=1e-6)
    assert multiplier == pytest.approx(SLOPE_AT_ZERO, rel=1e-6)


def test_interior_optimum_has_no_multiplier(design_space, subdivision) -> None:
    """Check that a box whose optimum is interior has a zero multiplier.

    Moving the face of such a box does not change its optimum.
    """
    relaxed = subdivision.create_relaxed_design_space(design_space)
    _, multiplier = _solve_box(subdivision, relaxed, 3)
    assert multiplier == pytest.approx(0.0, abs=1e-6)


def test_negative_margin(design_space, subdivision) -> None:
    """Check the error raised when the margin is negative."""
    with pytest.raises(ValueError, match=r"margin must be non-negative"):
        subdivision.create_relaxed_design_space(design_space, margin=-1.0)


def test_relaxed_design_space_is_a_copy(design_space, subdivision) -> None:
    """Check that the original design space is left untouched."""
    subdivision.create_relaxed_design_space(design_space)
    assert design_space.get_lower_bounds(["x"])[0] == pytest.approx(0.0)
    assert design_space.get_upper_bounds(["x"])[0] == pytest.approx(1.0)
