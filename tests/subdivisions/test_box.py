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
"""Tests for the Cartesian subdivision of a design space."""

from __future__ import annotations

import pytest
from gemseo.algos.design_space import DesignSpace
from numpy import array
from numpy import inf
from numpy import zeros
from numpy.testing import assert_allclose

from gemseo_box_subdivision.subdivisions.box import BoxSubdivision


@pytest.fixture
def design_space() -> DesignSpace:
    """A design space with a vector variable and a scalar one."""
    design_space = DesignSpace()
    design_space.add_variable("x", lower_bound=0.0, upper_bound=1.0, size=2, value=0.5)
    design_space.add_variable("y", lower_bound=-2.0, upper_bound=2.0, value=0.0)
    return design_space


def test_a_variable_of_several_components_is_subdivided_per_component() -> None:
    """Check that each component of an array variable carries its own bounds.

    The sizes are taken apart, three components and four subdivisions, since a
    square case cannot tell the bounds of a component from the bounds of a
    subdivision. Each component is subdivided over **its own** range, so the
    bounds of one say nothing about the bounds of another.
    """
    space = DesignSpace()
    space.add_variable(
        "x",
        lower_bound=array([0.0, -1.0, 10.0]),
        upper_bound=array([1.0, 1.0, 20.0]),
        size=3,
        value=array([0.5, 0.0, 15.0]),
    )
    subdivision = BoxSubdivision.from_design_space(space, 4)

    assert subdivision.get_lower_bounds("x").shape == (3, 4)
    assert subdivision.n_binaries == 12
    assert subdivision.n_boxes == 4**3
    assert_allclose(subdivision.get_lower_bounds("x")[1], [-1.0, -0.5, 0.0, 0.5])
    assert_allclose(subdivision.get_upper_bounds("x")[2], [12.5, 15.0, 17.5, 20.0])

    # A one-hot picking the first subdivision of the first component, the last of
    # the second and the second of the third: three independent choices.
    one_hot = zeros(12)
    for component, index in enumerate((0, 3, 1)):
        one_hot[component * 4 + index] = 1.0

    lower, upper = subdivision.compute_bounds("x", one_hot)
    assert_allclose(lower, [0.0, 0.5, 12.5])
    assert_allclose(upper, [0.25, 1.0, 15.0])
    assert_allclose(subdivision.locate("x", array([0.9, -0.9, 19.0])), [3, 0, 3])


def test_uniform_subdivision(design_space) -> None:
    """Check the bounds of a uniform subdivision."""
    subdivision = BoxSubdivision.from_design_space(design_space, 2)
    assert_allclose(subdivision.get_lower_bounds("x"), [[0.0, 0.5], [0.0, 0.5]])
    assert_allclose(subdivision.get_upper_bounds("x"), [[0.5, 1.0], [0.5, 1.0]])
    assert_allclose(subdivision.get_lower_bounds("y"), [[-2.0, 0.0]])
    assert_allclose(subdivision.get_upper_bounds("y"), [[0.0, 2.0]])


def test_subdivisions_are_contiguous(design_space) -> None:
    """Check that the subdivisions tile the original bounds without a gap."""
    subdivision = BoxSubdivision.from_design_space(design_space, 5)
    for name in subdivision.variable_names:
        lower_bounds = subdivision.get_lower_bounds(name)
        upper_bounds = subdivision.get_upper_bounds(name)
        assert_allclose(upper_bounds[:, :-1], lower_bounds[:, 1:])
        assert_allclose(lower_bounds[:, 0], design_space.get_lower_bounds([name]))
        assert_allclose(upper_bounds[:, -1], design_space.get_upper_bounds([name]))


def test_subdivision_per_variable(design_space) -> None:
    """Check that the number of subdivisions can differ from one variable to another."""
    subdivision = BoxSubdivision.from_design_space(design_space, {"x": 2, "y": 4})
    assert subdivision.n_subdivisions == {"x": 2, "y": 4}
    assert subdivision.sizes == {"x": 2, "y": 1}


def test_variable_names_subset(design_space) -> None:
    """Check that a subset of the design variables can be subdivided."""
    subdivision = BoxSubdivision.from_design_space(design_space, 2, ["y"])
    assert subdivision.variable_names == ("y",)


def test_counts(design_space) -> None:
    """Check the number of boxes and of binary variables.

    The number of boxes is exponential in the number of components, whereas the
    number of binaries, which sizes the master problem, is linear in it.
    """
    subdivision = BoxSubdivision.from_design_space(design_space, {"x": 2, "y": 4})
    # x has 2 components with 2 subdivisions, y has 1 component with 4.
    assert subdivision.n_boxes == 2 * 2 * 4
    assert subdivision.n_binaries == 2 * 2 + 1 * 4


def test_max_step(design_space) -> None:
    """Check the largest trust-region step, in the distance of the master.

    Every subdivision being weighed alike, the distance is the number of
    components a candidate changes, so its largest value is the number of
    components of the subdivision.
    """
    subdivision = BoxSubdivision.from_design_space(design_space, {"x": 2, "y": 4})
    # x has 2 components and y has 1.
    assert subdivision.max_step == 3


def test_single_subdivision(design_space) -> None:
    """Check that a single subdivision returns the original bounds."""
    subdivision = BoxSubdivision.from_design_space(design_space, 1)
    assert subdivision.n_boxes == 1
    assert_allclose(subdivision.get_lower_bounds("y"), [[-2.0]])
    assert_allclose(subdivision.get_upper_bounds("y"), [[2.0]])


def test_unknown_variable(design_space) -> None:
    """Check the error raised when a variable is not in the design space."""
    with pytest.raises(ValueError, match=r"not in the design space: \['z'\]"):
        BoxSubdivision.from_design_space(design_space, 2, ["z"])


def test_non_positive_n_subdivisions(design_space) -> None:
    """Check the error raised when the number of subdivisions is not positive."""
    with pytest.raises(
        ValueError, match=r"number of subdivisions of x must be positive; got 0"
    ):
        BoxSubdivision.from_design_space(design_space, 0)


def test_unbounded_variable() -> None:
    """Check the error raised when a variable is unbounded."""
    design_space = DesignSpace()
    design_space.add_variable("x", lower_bound=-inf, upper_bound=1.0, value=0.0)
    with pytest.raises(ValueError, match=r"x must have finite bounds"):
        BoxSubdivision.from_design_space(design_space, 2)


def test_inconsistent_variables() -> None:
    """Check the error raised when the bounds do not cover the same variables."""
    with pytest.raises(ValueError, match=r"same variables"):
        BoxSubdivision({"x": array([[0.0]])}, {"y": array([[1.0]])})


def test_no_variable() -> None:
    """Check the error raised when no variable is subdivided."""
    with pytest.raises(ValueError, match=r"at least one variable"):
        BoxSubdivision({}, {})


def test_inconsistent_shapes() -> None:
    """Check the error raised when the bounds have inconsistent shapes."""
    with pytest.raises(ValueError, match=r"same shape"):
        BoxSubdivision({"x": array([[0.0, 0.5]])}, {"x": array([[1.0]])})


def test_not_a_matrix() -> None:
    """Check the error raised when the bounds are not a matrix."""
    with pytest.raises(ValueError, match=r"must be a matrix"):
        BoxSubdivision({"x": array([0.0])}, {"x": array([1.0])})


def test_non_finite_bounds() -> None:
    """Check the error raised when the bounds are not finite."""
    with pytest.raises(ValueError, match=r"must be finite"):
        BoxSubdivision({"x": array([[-inf]])}, {"x": array([[1.0]])})


def test_empty_subdivision() -> None:
    """Check the error raised when a subdivision is empty."""
    with pytest.raises(ValueError, match=r"strictly smaller"):
        BoxSubdivision({"x": array([[1.0]])}, {"x": array([[1.0]])})


def test_one_hot_names(design_space) -> None:
    """Check the default and overridden names of the one-hot variables."""
    subdivision = BoxSubdivision.from_design_space(design_space, 2)
    assert subdivision.get_one_hot_names() == {"x": "x_box", "y": "y_box"}
    assert subdivision.get_one_hot_names({"x": "alpha"}) == {
        "x": "alpha",
        "y": "y_box",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([0.1, 0.9], [0, 3]),
        # A value on a border belongs to the first of the two subdivisions.
        ([0.25, 0.75], [0, 2]),
        # A value outside the bounds is assigned to the closest subdivision.
        ([-5.0, 5.0], [0, 3]),
        ([0.0, 1.0], [0, 3]),
    ],
)
def test_locate(design_space, value, expected) -> None:
    """Check the subdivision containing a value."""
    subdivision = BoxSubdivision.from_design_space(design_space, 4)
    assert list(subdivision.locate("x", array(value))) == expected


def test_relaxed_design_space_keeps_other_variables(design_space) -> None:
    """Check that a variable that is not subdivided keeps its bounds."""
    subdivision = BoxSubdivision.from_design_space(design_space, 2, ["y"])
    relaxed = subdivision.create_relaxed_design_space(design_space)
    assert_allclose(relaxed.get_lower_bounds(["x"]), [0.0, 0.0])
    assert_allclose(relaxed.get_upper_bounds(["x"]), [1.0, 1.0])
    assert relaxed.get_lower_bounds(["y"])[0] < -2.0
