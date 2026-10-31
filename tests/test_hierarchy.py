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
"""Tests for the hierarchies of subdivisions."""

from __future__ import annotations

import itertools

import pytest
from gemseo.space import DesignSpace
from numpy import array
from numpy import full
from numpy import zeros

from gemseo_box_subdivision.hierarchy import RANKINGS
from gemseo_box_subdivision.hierarchy import SHAPES
from gemseo_box_subdivision.hierarchy import SolvedBox
from gemseo_box_subdivision.hierarchy import compute_cut_model
from gemseo_box_subdivision.hierarchy import refine_deep
from gemseo_box_subdivision.hierarchy import refine_frontier
from gemseo_box_subdivision.hierarchy import refine_two_levels
from gemseo_box_subdivision.subdivisions.box import BoxSubdivision


def _subdivision(lower, upper, n_subdivisions: int) -> BoxSubdivision:
    """Return a subdivision of a one-variable design space."""
    space = DesignSpace()
    space.add_variable(
        "x", lower_bound=lower, upper_bound=upper, size=lower.size, value=lower
    )
    return BoxSubdivision.from_design_space(space, n_subdivisions)


def _one_hot(index: int, n_subdivisions: int, size: int = 1):
    """Return the one-hot vector selecting a box."""
    vector = zeros((size, n_subdivisions))
    vector[:, index] = 1.0
    return vector.ravel()


@pytest.fixture
def solver():
    """A solver whose value decreases towards the left of any region."""
    calls = []

    def solve(lower, upper, n_subdivisions):
        subdivision = _subdivision(lower, upper, n_subdivisions)
        calls.append((lower.copy(), upper.copy(), n_subdivisions))
        solved = [
            SolvedBox(
                _one_hot(index, n_subdivisions),
                float(index),
                full(n_subdivisions, 0.5),
            )
            for index in range(n_subdivisions)
        ]
        return subdivision, solved

    solve.calls = calls
    return solve


def test_deep_descends_and_narrows(solver) -> None:
    """Each level must sit inside the one above and be narrower."""
    visited = refine_deep(
        solver, array([0.0]), array([1.0]), branching=2, depth=3, ranking="value"
    )
    assert len(visited) == 4
    for (lower, upper), (next_lower, next_upper) in itertools.pairwise(visited):
        assert next_lower >= lower - 1e-12
        assert next_upper <= upper + 1e-12
        assert next_upper - next_lower < upper - lower


def test_deep_follows_the_ranking(solver) -> None:
    """Ranking by value must descend into the lowest-valued box, the leftmost here."""
    visited = refine_deep(solver, array([0.0]), array([1.0]), branching=2, depth=3)
    # Halving the left half each time.
    assert visited[-1][0] == pytest.approx(0.0)
    assert visited[-1][1] == pytest.approx(0.125)


def test_a_level_without_a_solved_box_stops_the_search() -> None:
    """Returning no solved box must end the search, which is how a budget ends it."""

    def solve(lower, upper, n_subdivisions):
        return _subdivision(lower, upper, n_subdivisions), []

    visited = refine_deep(solve, array([0.0]), array([1.0]), depth=5)
    assert len(visited) == 1


def test_two_levels_refines_the_requested_number(solver) -> None:
    """The coarse level must be followed by one fine level per refined box."""
    visited = refine_two_levels(
        solver, array([0.0]), array([1.0]), coarse=4, fine=3, n_refined=2
    )
    assert len(visited) == 3
    assert [call[2] for call in solver.calls] == [4, 3, 3]


def test_frontier_can_return_to_a_box_it_passed_over(solver) -> None:
    """The frontier must expand boxes that are not descendants of the last one."""
    visited = refine_frontier(
        solver, array([0.0]), array([1.0]), branching=2, expansions=5, n_children=2
    )
    assert len(visited) == 5
    # A purely descending search would nest every region in the previous one.
    nested = all(
        later[0] >= earlier[0] - 1e-12 and later[1] <= earlier[1] + 1e-12
        for earlier, later in itertools.pairwise(visited)
    )
    assert not nested


def test_cut_model_covers_every_box(solver) -> None:
    """The cut model must be defined at the boxes the master never solved."""
    subdivision, solved = solver(array([0.0]), array([1.0]), 5)
    boxes, model = compute_cut_model(solved[:2], subdivision)
    assert len(boxes) == 5
    assert len(model) == 5


@pytest.mark.parametrize("ranking", sorted(RANKINGS))
def test_every_ranking_returns_boxes(solver, ranking) -> None:
    """Each rule must return one-hot vectors of the right width."""
    subdivision, solved = solver(array([0.0]), array([1.0]), 4)
    ranked = RANKINGS[ranking](solved, subdivision)
    assert ranked
    assert all(box.size == 4 for box in ranked)


def test_shapes_are_registered() -> None:
    """The three shapes must be reachable by name."""
    assert set(SHAPES) == {"deep", "two_levels", "frontier"}
