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
"""Tests for the mapping from the levels of a multi-resolution subdivision."""

from __future__ import annotations

import pytest
from gemseo import check_jacobian
from numpy import array
from numpy.random import default_rng
from numpy.testing import assert_allclose

from gemseo_box_subdivision.disciplines.multi_resolution_mapping import (
    MultiResolutionMapping,
)
from gemseo_box_subdivision.subdivisions.multi_resolution import MultiResolution


@pytest.fixture
def subdivision() -> MultiResolution:
    """A subdivision of a two-dimensional design space into two levels of four."""
    return MultiResolution(
        {"x": array([-4.1, -4.1])}, {"x": array([5.9, 5.9])}, branching=4, levels=2
    )


def test_grammar(subdivision) -> None:
    """The mapping must read one one-hot per level and write the design variable."""
    discipline = MultiResolutionMapping(subdivision)
    for level in range(1, subdivision.levels + 1):
        assert subdivision.get_one_hot_name("x", level) in discipline.io.input_grammar

    assert subdivision.get_normalized_name("x") in discipline.io.input_grammar
    assert "x" in discipline.io.output_grammar


def test_maps_to_the_selected_box(subdivision) -> None:
    """The normalized point must be placed inside the box the levels select."""
    discipline = MultiResolutionMapping(subdivision)
    point = array([1.3, -2.7])
    one_hots = subdivision.locate("x", point)
    lower_bound, upper_bound = subdivision.compute_bounds("x", one_hots)
    data = {
        subdivision.get_one_hot_name("x", level + 1): one_hot
        for level, one_hot in enumerate(one_hots)
    }
    data[subdivision.get_normalized_name("x")] = array([0.0, 1.0])
    mapped = discipline.execute(data)["x"]
    assert_allclose(mapped, array([lower_bound[0], upper_bound[1]]))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_jacobian_at_relaxed_one_hots(subdivision, seed) -> None:
    """The Jacobian must hold where the master relaxes the one-hot variables.

    The master solves a relaxation, so the derivatives are needed at fractional
    one-hot values and not only at the vertices.
    """
    discipline = MultiResolutionMapping(subdivision)
    generator = default_rng(seed)
    data = {}
    for level in range(1, subdivision.levels + 1):
        relaxed = generator.uniform(0.1, 0.9, 2 * subdivision.branching).reshape(
            2, subdivision.branching
        )
        data[subdivision.get_one_hot_name("x", level)] = (
            relaxed / relaxed.sum(axis=1, keepdims=True)
        ).ravel()

    data[subdivision.get_normalized_name("x")] = generator.uniform(0.0, 1.0, 2)
    assert check_jacobian(discipline, input_value=data, atol=1e-6, rtol=1e-6, step=1e-7)
