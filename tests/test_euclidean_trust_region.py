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
"""Tests for the Euclidean trust region as an option of the settings."""

from __future__ import annotations

import pytest
from gemseo_bilevel_outer_approximation.algos.opt.core import (
    outer_approximation_optimizer as core,
)

from gemseo_box_subdivision import BoxSubdivisionScenario
from gemseo_box_subdivision import BoxSubdivisionSettings
from gemseo_box_subdivision import MultiResolution
from gemseo_box_subdivision import SweptBoxSubdivisionSettings
from gemseo_box_subdivision._euclidean_trust_region import _PATCHED
from gemseo_box_subdivision._euclidean_trust_region import box_distance
from tests.test_scenario import Rastrigin
from tests.test_scenario import best
from tests.test_scenario import design_space


def test_the_hamming_metric_is_the_default() -> None:
    """The default settings must keep the Hamming trust region."""
    settings = BoxSubdivisionSettings()
    assert settings.trust_region_metric == "hamming"
    assert settings.euclidean_trust_region() is None


@pytest.mark.parametrize(
    ("settings", "match"),
    [
        ({"trust_region_metric": "manhattan"}, "trust_region_metric"),
        ({"trust_region_anchor": "nearest"}, "Euclidean trust region only"),
        ({"trust_region_schedule": "diameter"}, "Euclidean trust region only"),
        ({"trust_region_radius": 1.5}, "integer"),
        (
            {"trust_region_metric": "euclidean", "trust_region_anchor": "farthest"},
            "trust_region_anchor",
        ),
    ],
)
def test_an_inconsistent_trust_region_is_refused(settings, match) -> None:
    """An unknown option, or a Euclidean option on the Hamming metric, is refused.

    Args:
        settings: The settings of the trust region.
        match: What the error must say.
    """
    with pytest.raises(ValueError, match=match):
        BoxSubdivisionSettings(**settings)


def test_the_euclidean_options_reach_the_region() -> None:
    """The radius, the anchor and the schedule must reach the trust region."""
    region = SweptBoxSubdivisionSettings(
        trust_region_metric="euclidean",
        trust_region_radius=1.5,
        trust_region_anchor="nearest",
        trust_region_schedule="diameter",
    ).euclidean_trust_region()
    assert region.initial_radius == pytest.approx(1.5)
    assert region.anchor == "nearest"
    assert region.schedule == "diameter"


def test_the_master_is_given_an_integer_step() -> None:
    """A Euclidean radius must reach the master as a valid integer step."""
    settings = BoxSubdivisionSettings(
        trust_region_metric="euclidean", trust_region_radius=1.5
    )
    assert settings.to_master_settings()["max_step"] == 2


@pytest.mark.parametrize("anchor", ["incumbent", "nearest"])
def test_a_euclidean_run_stays_in_its_region(monkeypatch, anchor) -> None:
    """Every box proposed by a Euclidean run must lie in its region.

    The region is the ball around the incumbent, or the union of the balls
    around the evaluated boxes, of the radius of the probe or, for the relaxed
    fallback, of the master. The master must be put back afterwards.

    Args:
        monkeypatch: The fixture patching the master.
        anchor: The box the distance is measured from.
    """
    proposals = []
    optimizer = core.OuterApproximationOptimizer
    originals = {name: getattr(optimizer, name) for name in _PATCHED}
    solve = optimizer._solve_milp

    def spy(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        alpha, eta, feasible = solve(self, *args, **kwargs)
        step = kwargs.get("current_step", args[14] if len(args) > 14 else None)
        anchors = [*args[1], *args[11]] if anchor == "nearest" else [args[13]]
        if feasible and step is not None and anchors:
            radius = max(step, self.current_step)
            distance = min(box_distance([10, 10], box, alpha) for box in anchors)
            proposals.append((distance, radius))
        return alpha, eta, feasible

    monkeypatch.setattr(optimizer, "_solve_milp", spy)
    scenario = BoxSubdivisionScenario(
        [Rastrigin()],
        "f",
        design_space(),
        n_subdivisions=10,
        settings=BoxSubdivisionSettings(
            trust_region_metric="euclidean",
            trust_region_radius=1.5,
            trust_region_anchor=anchor,
            max_iter=15,
        ),
    )
    scenario.execute()

    assert proposals
    assert all(distance <= radius + 1e-6 for distance, radius in proposals)
    assert best(scenario) < 20.0
    for name, original in originals.items():
        assert getattr(optimizer, name) is original


def test_the_multi_resolution_encoding_refuses_the_euclidean_metric() -> None:
    """The digits of a multi-resolution encoding are not positions of boxes."""
    scenario = BoxSubdivisionScenario(
        [Rastrigin()],
        "f",
        design_space(),
        n_subdivisions=4,
        levels=2,
        settings=BoxSubdivisionSettings(trust_region_metric="euclidean"),
    )
    assert isinstance(scenario.subdivision, MultiResolution)
    with pytest.raises(ValueError, match="multi-resolution"):
        scenario.execute()
