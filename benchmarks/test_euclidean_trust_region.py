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
"""Tests for the Euclidean trust region of the master."""

from __future__ import annotations

import logging
from math import isfinite
from math import sqrt

import pytest
from gemseo_bilevel_outer_approximation.algos.opt.core import (
    outer_approximation_optimizer as core,
)
from numpy import array
from numpy import concatenate
from numpy import eye
from numpy.testing import assert_allclose

from benchmarks.euclidean_trust_region import _PATCHED
from benchmarks.euclidean_trust_region import EuclideanTrustRegion
from benchmarks.euclidean_trust_region import box_distance
from benchmarks.euclidean_trust_region import cell
from benchmarks.euclidean_trust_region import diameter
from benchmarks.euclidean_trust_region import euclidean_trust_region
from benchmarks.euclidean_trust_region import run
from benchmarks.euclidean_trust_region import squared_distance_coefficients
from benchmarks.problems import PROBLEMS


def _box(blocks, indexes):  # noqa: ANN001, ANN202
    """Return the one-hot encoding of a box.

    Args:
        blocks: The number of intervals of each component.
        indexes: The interval of each component.

    Returns:
        The one-hot encoding.
    """
    return concatenate([
        eye(size)[index] for size, index in zip(blocks, indexes, strict=True)
    ])


def test_the_squared_distance_is_linear_in_the_candidate() -> None:
    """Check the coefficients against the distance between the centres."""
    blocks = [4, 4]
    incumbent = _box(blocks, (1, 2))
    assert_allclose(
        squared_distance_coefficients(blocks, incumbent),
        [1, 0, 1, 4, 4, 1, 0, 1],
    )
    for indexes in ((1, 2), (2, 2), (0, 3), (3, 0)):
        candidate = _box(blocks, indexes)
        expected = sqrt((indexes[0] - 1) ** 2 + (indexes[1] - 2) ** 2)
        assert box_distance(blocks, incumbent, candidate) == pytest.approx(expected)
        assert box_distance(blocks, candidate, incumbent) == pytest.approx(expected)


def test_the_unit_cube_charges_a_finer_component_less() -> None:
    """Check the two normalizations with unequal densities."""
    blocks = [2, 4]
    incumbent = _box(blocks, (0, 0))
    candidate = _box(blocks, (1, 2))
    # One coarse width, and two fine widths, which are one coarse width.
    assert box_distance(blocks, incumbent, candidate) == pytest.approx(sqrt(2))
    assert box_distance(blocks, incumbent, candidate, "interval") == pytest.approx(
        sqrt(5)
    )


@pytest.mark.parametrize(
    "settings",
    [
        {"normalization": "manhattan"},
        {"min_radius": 0.0},
        {"min_radius": 3.0},
        {"max_radius": 1.0},
        {"shrink_factor": 1.0},
        {"growth_factor": 0.9},
        {"schedule": "random"},
    ],
)
def test_the_settings_are_checked(settings) -> None:
    """Check that an inconsistent schedule is refused.

    Args:
        settings: The settings to try.
    """
    with pytest.raises(ValueError, match=r"must"):
        EuclideanTrustRegion(**settings)


def test_the_ceiling_defaults_to_the_initial_radius() -> None:
    """Check that the region grows back to where it started, as the master's."""
    assert EuclideanTrustRegion(initial_radius=3.0).ceiling == pytest.approx(3.0)
    assert EuclideanTrustRegion(
        initial_radius=3.0, max_radius=4.0
    ).ceiling == pytest.approx(4.0)


def test_the_master_is_put_back() -> None:
    """Check that the patched methods are restored on exit."""
    optimizer = core.OuterApproximationOptimizer
    originals = [getattr(optimizer, name) for name in _PATCHED]
    with euclidean_trust_region():
        assert all(
            getattr(optimizer, name) is not original
            for name, original in zip(_PATCHED, originals, strict=True)
        )

    assert all(
        getattr(optimizer, name) is original
        for name, original in zip(_PATCHED, originals, strict=True)
    )


def test_every_proposal_lies_in_the_ball(monkeypatch) -> None:
    """Check that the master proposes no box outside the radius it was given.

    Args:
        monkeypatch: The fixture patching the master.
    """
    logging.disable(logging.CRITICAL)
    proposals = []
    region = EuclideanTrustRegion(initial_radius=2.0)
    optimizer = core.OuterApproximationOptimizer
    solve = optimizer._solve_milp

    def spy(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        alpha, eta, feasible = solve(self, *args, **kwargs)
        incumbent = args[13]
        step = kwargs.get("current_step", args[14] if len(args) > 14 else None)
        if feasible and step is not None:
            # The relaxed fallback uses the radius of the master.
            radius = max(step, self.current_step)
            proposals.append((box_distance([10, 10], incumbent, alpha), radius))
        return alpha, eta, feasible

    # The run enters the Euclidean trust region itself, around the spy.
    monkeypatch.setattr(optimizer, "_solve_milp", spy)
    outcome = run(PROBLEMS["rastrigin"], 2, 11, 300, 10, region)

    logging.disable(logging.NOTSET)
    assert proposals
    assert all(distance <= radius + 1e-6 for distance, radius in proposals)
    # Not only the face neighbours: the ball admits the diagonal ones too.
    assert any(distance > 1 for distance, _ in proposals)
    assert isfinite(outcome.best)


def test_a_cell_reads_as_the_tables() -> None:
    """Check the format of a cell."""
    assert cell([0.0, 1e-5, 2.0], [10, 30, 20]) == "$0.000$ · 20 · 2/3"
    assert cell([], []) == "failed"


def test_the_box_encoding_is_concatenated_per_component() -> None:
    """Check the helper the other tests rely on."""
    assert_allclose(_box([2, 3], (1, 0)), array([0, 1, 1, 0, 0]))


def test_the_diameter_joins_the_centres_of_opposite_corners() -> None:
    """Check the diameter, with equal and unequal densities."""
    assert diameter([10] * 5) == pytest.approx(9 * sqrt(5))
    # Three coarse widths along the first, seven half-widths along the second.
    assert diameter([4, 8]) == pytest.approx(sqrt(3**2 + 3.5**2))
    assert diameter([4, 8], "interval") == pytest.approx(sqrt(3**2 + 7**2))


def test_the_diameter_schedule_spreads_the_probes_down_to_the_floor() -> None:
    """Check the probes of the diameter schedule and of the fixed one."""
    region = EuclideanTrustRegion(schedule="diameter")
    blocks = [10] * 5
    radius = region.initial_radius_of(blocks)
    assert radius == pytest.approx(9 * sqrt(5))
    assert region.max_radius_of(blocks) == pytest.approx(radius)
    probes = region.probe_radii(radius, 4, 5)
    assert probes[0] == pytest.approx(radius / (2 * sqrt(5)))
    assert probes[-1] == pytest.approx(radius)
    # Every probe is floored at one width, and a radius below the floor too.
    assert_allclose(region.probe_radii(3.0, 4, 5), [1.0, 1.442, 2.080, 3.0], 1e-3)
    assert_allclose(region.probe_radii(0.5, 4, 5), [1.0] * 4)
    assert_allclose(
        EuclideanTrustRegion().probe_radii(3.0, 3, 5), [1.5, 2.121, 3], 1e-3
    )
    assert_allclose(region.probe_radii(3.0, 1, 5), [3.0])


def test_the_diameter_schedule_gives_the_probes_their_radii(monkeypatch) -> None:
    """Check that the probes of a run are solved at the radii of the schedule.

    Args:
        monkeypatch: The fixture patching the master.
    """
    logging.disable(logging.CRITICAL)
    radii = []
    region = EuclideanTrustRegion(schedule="diameter")
    optimizer = core.OuterApproximationOptimizer
    build = optimizer._build_milp_problem

    def spy(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        radii.append((args[-1], self.current_step))
        return build(self, *args, **kwargs)

    # Installed before the region, so that the region calls the spy.
    monkeypatch.setattr(optimizer, "_build_milp_problem", spy)
    run(PROBLEMS["rastrigin"], 2, 11, 300, 10, region)
    logging.disable(logging.NOTSET)
    for radius, current in radii:
        expected = region.probe_radii(current, 4, 2)
        assert min(abs(expected - radius)) == pytest.approx(0.0, abs=1e-9)

    assert {round(radius, 3) for radius, _ in radii} >= {4.5, 12.728}


def test_every_proposal_lies_near_an_evaluated_box(monkeypatch) -> None:
    """Check that the nearest anchor admits only boxes near an evaluated box.

    The proposals must lie within the radius of at least one evaluated box, and
    at least one of them must lie outside the ball around the incumbent, which
    the union of balls admits and the single ball does not.

    Args:
        monkeypatch: The fixture patching the master.
    """
    logging.disable(logging.CRITICAL)
    proposals = []
    region = EuclideanTrustRegion(initial_radius=1.5, anchor="nearest")
    optimizer = core.OuterApproximationOptimizer
    solve = optimizer._solve_milp

    def spy(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        alpha, eta, feasible = solve(self, *args, **kwargs)
        step = kwargs.get("current_step", args[14] if len(args) > 14 else None)
        evaluated = [*args[1], *args[11]]
        if feasible and step is not None and evaluated:
            radius = max(step, self.current_step)
            nearest = min(box_distance([10, 10], box, alpha) for box in evaluated)
            incumbent = box_distance([10, 10], args[13], alpha)
            proposals.append((nearest, incumbent, radius))
        return alpha, eta, feasible

    monkeypatch.setattr(optimizer, "_solve_milp", spy)
    outcome = run(PROBLEMS["rastrigin"], 2, 11, 300, 10, region)

    logging.disable(logging.NOTSET)
    assert proposals
    assert all(nearest <= radius + 1e-6 for nearest, _, radius in proposals)
    assert any(incumbent > radius + 1e-6 for _, incumbent, radius in proposals)
    assert isfinite(outcome.best)


def test_the_anchor_is_checked() -> None:
    """Check that an unknown anchor is rejected."""
    with pytest.raises(ValueError, match="anchor"):
        EuclideanTrustRegion(anchor="farthest")
