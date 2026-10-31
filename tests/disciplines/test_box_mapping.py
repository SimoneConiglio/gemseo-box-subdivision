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
"""Tests for the mapping from the normalized variables of a box."""

from __future__ import annotations

import pytest
from gemseo import check_jacobian
from gemseo.space import DesignSpace
from numpy import array
from numpy import zeros
from numpy.random import default_rng
from numpy.testing import assert_allclose

from gemseo_box_subdivision.disciplines.box_mapping import BoxMapping
from gemseo_box_subdivision.subdivisions.box import BoxSubdivision


@pytest.fixture
def subdivision() -> BoxSubdivision:
    """A subdivision of a vector variable and a scalar one."""
    design_space = DesignSpace()
    design_space.add_variable("x", lower_bound=0.0, upper_bound=1.0, size=2, value=0.5)
    design_space.add_variable("y", lower_bound=-2.0, upper_bound=2.0, value=0.0)
    return BoxSubdivision.from_design_space(design_space, {"x": 2, "y": 4})


@pytest.fixture
def discipline(subdivision) -> BoxMapping:
    """The mapping of the subdivision."""
    return BoxMapping(subdivision)


def test_io_names(discipline) -> None:
    """Check the inputs and outputs of the discipline."""
    assert set(discipline.io.input_grammar.names) == {
        "x_normalized",
        "x_box",
        "y_normalized",
        "y_box",
    }
    assert set(discipline.io.output_grammar.names) == {"x", "y"}
    assert discipline.normalized_names == {"x": "x_normalized", "y": "y_normalized"}
    assert discipline.one_hot_names == {"x": "x_box", "y": "y_box"}


def test_custom_names(subdivision) -> None:
    """Check that the variable names can be customized."""
    discipline = BoxMapping(
        subdivision, one_hot_names={"x": "alpha"}, normalized_names={"x": "xi"}
    )
    assert "alpha" in discipline.io.input_grammar.names
    assert "xi" in discipline.io.input_grammar.names


def test_default_is_the_box_center(discipline) -> None:
    """Check that the default normalized value is the center of the box."""
    output_data = discipline.execute()
    assert_allclose(output_data["x"], [0.25, 0.25])
    assert_allclose(output_data["y"], [-1.5])


@pytest.mark.parametrize(
    ("index", "normalized", "expected"),
    [(0, 0.0, -2.0), (0, 1.0, -1.0), (2, 0.25, 0.25), (3, 0.5, 1.5)],
)
def test_mapping(discipline, index, normalized, expected) -> None:
    """Check the mapping onto the selected box."""
    one_hot = zeros(4)
    one_hot[index] = 1.0
    output_data = discipline.execute({
        "y_normalized": array([normalized]),
        "y_box": one_hot,
    })
    assert output_data["y"][0] == pytest.approx(expected)


@pytest.mark.parametrize("index", range(4))
def test_unit_interval_covers_the_box(discipline, subdivision, index) -> None:
    """Check that the unit interval maps exactly onto the selected box.

    This is what makes the box a bound of the sub-problem rather than a
    constraint, and what makes those bounds independent of the box.
    """
    one_hot = zeros(4)
    one_hot[index] = 1.0
    lower = discipline.execute({"y_normalized": array([0.0]), "y_box": one_hot})["y"]
    upper = discipline.execute({"y_normalized": array([1.0]), "y_box": one_hot})["y"]
    assert_allclose(lower, subdivision.get_lower_bounds("y")[:, index])
    assert_allclose(upper, subdivision.get_upper_bounds("y")[:, index])


@pytest.mark.parametrize(
    ("approximation", "step", "threshold"),
    [("finite_differences", 1e-7, 1e-5), ("complex_step", 1e-30, 1e-10)],
)
def test_jacobian(discipline, approximation, step, threshold) -> None:
    """Check the analytic Jacobian of the mapping.

    The one-hot values are drawn at random in [0, 1] rather than set to a vertex,
    because the master problem relaxes them.
    """
    rng = default_rng(0)
    assert check_jacobian(
        discipline,
        input_value={
            "x_normalized": rng.random(2),
            "y_normalized": rng.random(1),
            "x_box": rng.random(4),
            "y_box": rng.random(4),
        },
        approximation_mode=approximation,
        step=step,
        atol=threshold,
        rtol=threshold,
    )


def test_sensitivity_coefficients(discipline) -> None:
    """Check the derivative of the mapping w.r.t. the one-hot vector.

    At the center of a box, the derivative with respect to a subdivision is the
    center of that subdivision, since the mapping interpolates the bounds.
    """
    discipline.linearize(execute=True, compute_all_jacobians=True)
    jacobian = discipline.jac["y"]["y_box"]
    # The four subdivisions of y over [-2, 2] have centers -1.5, -0.5, 0.5, 1.5.
    assert_allclose(jacobian[0], [-1.5, -0.5, 0.5, 1.5])
    # The derivative with respect to the normalized variable is the box width.
    assert_allclose(discipline.jac["y"]["y_normalized"], [[1.0]])
