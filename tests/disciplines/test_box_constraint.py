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
"""Tests for the box constraint."""

from __future__ import annotations

import pytest
from gemseo import check_jacobian
from gemseo.space import DesignSpace
from numpy import array
from numpy import zeros
from numpy.random import default_rng
from numpy.testing import assert_allclose

from gemseo_box_subdivision.disciplines.box_constraint import BoxConstraint
from gemseo_box_subdivision.subdivisions.box import BoxSubdivision


@pytest.fixture
def subdivision() -> BoxSubdivision:
    """A subdivision of a vector variable and a scalar one."""
    design_space = DesignSpace()
    design_space.add_variable("x", lower_bound=0.0, upper_bound=1.0, size=2, value=0.5)
    design_space.add_variable("y", lower_bound=-2.0, upper_bound=2.0, value=0.0)
    return BoxSubdivision.from_design_space(design_space, {"x": 2, "y": 4})


@pytest.fixture
def discipline(subdivision) -> BoxConstraint:
    """The box constraint of the subdivision."""
    return BoxConstraint(subdivision)


def test_io_names(discipline) -> None:
    """Check the inputs and outputs of the discipline."""
    assert set(discipline.io.input_grammar.names) == {"x", "x_box", "y", "y_box"}
    assert set(discipline.io.output_grammar.names) == {"g_box"}
    assert discipline.one_hot_names == {"x": "x_box", "y": "y_box"}
    assert discipline.output_name == "g_box"


def test_custom_names(subdivision) -> None:
    """Check that the one-hot and output names can be customized."""
    discipline = BoxConstraint(
        subdivision, one_hot_names={"x": "alpha_x"}, output_name="box"
    )
    assert set(discipline.io.input_grammar.names) == {"x", "alpha_x", "y", "y_box"}
    assert set(discipline.io.output_grammar.names) == {"box"}


def test_default_execution(discipline) -> None:
    """Check that the default point is at the center of the first box."""
    # x starts at 0.25 in [0, 0.5] and y at -1.5 in [-2, -1].
    assert_allclose(
        discipline.execute()["g_box"], [-0.25, -0.25, -0.5, -0.25, -0.25, -0.5]
    )


def test_constraint_ordering(discipline) -> None:
    """Check that the upper faces come first and the lower faces last."""
    # Select the second subdivision of both components of x, i.e. [0.5, 1].
    one_hot = zeros((2, 2))
    one_hot[:, 1] = 1.0
    g_box = discipline.execute({
        "x": array([0.5, 1.0]),
        "x_box": one_hot.ravel(),
    })["g_box"]
    # x is on the lower face of its box for the first component,
    # and on the upper face for the second one.
    assert_allclose(g_box[:2], [-0.5, 0.0])
    assert_allclose(g_box[3:5], [0.0, -0.5])


@pytest.mark.parametrize(
    ("component", "index", "expected_bounds"),
    [(0, 0, (-2.0, -1.0)), (0, 2, (0.0, 1.0)), (0, 3, (1.0, 2.0))],
)
def test_selected_box(discipline, component, index, expected_bounds) -> None:
    """Check that the one-hot vector selects the expected box."""
    one_hot = zeros((1, 4))
    one_hot[component, index] = 1.0
    lower_bound, upper_bound = expected_bounds
    # The constraint vanishes exactly on the faces of the selected box.
    g_box = discipline.execute({
        "y": array([upper_bound]),
        "y_box": one_hot.ravel(),
    })["g_box"]
    assert g_box[2] == pytest.approx(0.0)
    assert g_box[5] == pytest.approx(lower_bound - upper_bound)


def test_feasibility_inside_and_outside(discipline) -> None:
    """Check the sign of the constraint inside and outside the selected box."""
    one_hot = zeros((1, 4))
    one_hot[0, 2] = 1.0
    inside = discipline.execute({"y": array([0.5]), "y_box": one_hot.ravel()})["g_box"]
    assert (inside[[2, 5]] <= 0.0).all()

    outside = discipline.execute({"y": array([1.5]), "y_box": one_hot.ravel()})["g_box"]
    assert outside[2] > 0.0


@pytest.mark.parametrize(
    ("approximation", "step", "threshold"),
    [("finite_differences", 1e-7, 1e-5), ("complex_step", 1e-30, 1e-10)],
)
def test_jacobian(discipline, approximation, step, threshold) -> None:
    """Check the analytic Jacobian of the constraint.

    The one-hot values are drawn at random in [0, 1] rather than set to a vertex,
    because the master problem relaxes them and the outer-approximation cuts are
    built from this Jacobian.
    """
    rng = default_rng(0)
    assert check_jacobian(
        discipline,
        input_value={
            "x": array([0.3, 0.8]),
            "y": array([0.4]),
            "x_box": rng.random(4),
            "y_box": rng.random(4),
        },
        approximation_mode=approximation,
        step=step,
        atol=threshold,
        rtol=threshold,
    )


def test_jacobian_is_constant(discipline) -> None:
    """Check that the Jacobian does not depend on the point.

    The constraint is linear in the design variables and affine in the one-hot
    vectors, so its Jacobian is constant.
    """
    rng = default_rng(1)
    discipline.linearize(
        {
            "x": array([0.1, 0.2]),
            "y": array([0.3]),
            "x_box": rng.random(4),
            "y_box": rng.random(4),
        },
        execute=True,
        compute_all_jacobians=True,
    )
    first = {key: value.copy() for key, value in discipline.jac["g_box"].items()}
    discipline.linearize(
        {
            "x": array([0.9, 0.7]),
            "y": array([-1.0]),
            "x_box": rng.random(4),
            "y_box": rng.random(4),
        },
        execute=True,
        compute_all_jacobians=True,
    )
    for name, jacobian in discipline.jac["g_box"].items():
        assert_allclose(jacobian, first[name])


def test_sensitivity_coefficients(discipline) -> None:
    """Check the derivative of the constraint w.r.t. the one-hot vector.

    The rows w.r.t. the one-hot vector carry the subdivision bounds, which is
    what turns the constraint multipliers into the sensitivity of the
    sub-problem optimum w.r.t. the box selection.
    """
    discipline.linearize(execute=True, compute_all_jacobians=True)
    jacobian = discipline.jac["g_box"]["y_box"]
    # y is the third component, and has 4 subdivisions of width 1 over [-2, 2].
    assert_allclose(jacobian[2], [1.0, 0.0, -1.0, -2.0])
    assert_allclose(jacobian[5], [-2.0, -1.0, 0.0, 1.0])
