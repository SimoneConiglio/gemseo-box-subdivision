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
"""Tests for the interface shared by the subdivisions of a design space."""

from __future__ import annotations

import pytest
from numpy import array

from gemseo_box_subdivision.subdivisions.base import BaseSubdivision
from gemseo_box_subdivision.subdivisions.box import BoxSubdivision
from gemseo_box_subdivision.subdivisions.multi_resolution import MultiResolution


@pytest.mark.parametrize(
    "subdivision",
    [
        BoxSubdivision({"x": array([[0.0, 1.0]])}, {"x": array([[1.0, 2.0]])}),
        MultiResolution(
            {"x": array([0.0])}, {"x": array([2.0])}, branching=2, levels=1
        ),
    ],
)
def test_subdivisions_share_the_interface(subdivision) -> None:
    """Check that both subdivisions implement the interface."""
    assert isinstance(subdivision, BaseSubdivision)
    assert subdivision.variable_names == ("x",)
    assert subdivision.sizes == {"x": 1}
    assert subdivision.n_boxes == 2
    assert subdivision.n_binaries == 2
    assert subdivision.max_step == 1


def test_cannot_be_instantiated() -> None:
    """Check that the interface is abstract."""
    with pytest.raises(TypeError):
        BaseSubdivision()
