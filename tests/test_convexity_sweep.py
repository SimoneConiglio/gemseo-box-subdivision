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
"""Tests for the ladder of convexity values and the rule redeploying its probes."""

from __future__ import annotations

import pytest
from numpy import inf
from numpy import nan

from gemseo_box_subdivision import BoxSubdivisionSettings
from gemseo_box_subdivision import ConvexitySweep
from gemseo_box_subdivision import ConvexitySweepSettings
from gemseo_box_subdivision import convexity_ladder
from gemseo_box_subdivision import objective_scale
from gemseo_box_subdivision.convexity_sweep import LADDER_DECADES


def test_ladder_ends_at_the_upper_bound() -> None:
    """Check that the ladder spans its decades and ends at the upper bound."""
    ladder = convexity_ladder(100.0, 4)
    assert ladder[-1] == pytest.approx(100.0)
    assert ladder[0] == pytest.approx(100.0 / 10.0**LADDER_DECADES)
    assert list(ladder) == sorted(ladder)


def test_ladder_of_a_single_point() -> None:
    """Check that a single point is the value it would replace."""
    assert convexity_ladder(80.0, 1) == (80.0,)


def test_ladder_span() -> None:
    """Check that the span of the ladder is the number of decades asked for."""
    ladder = convexity_ladder(100.0, 3, decades=4.0)
    assert ladder[0] == pytest.approx(0.01)
    assert ladder[-1] == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("max_value", "n_points", "decades", "match"),
    [
        (0.0, 4, 2.0, r"upper bound of the sweep must be positive"),
        (-1.0, 4, 2.0, r"upper bound of the sweep must be positive"),
        (10.0, 0, 2.0, r"number of rungs must be positive"),
        (10.0, 4, -1.0, r"span of the ladder must be non-negative"),
    ],
)
def test_ladder_errors(max_value, n_points, decades, match) -> None:
    """Check the errors raised by an unusable ladder."""
    with pytest.raises(ValueError, match=match):
        convexity_ladder(max_value, n_points, decades)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((1.0, 5.0, 3.0), 4.0),
        ((), 0.0),
        ((2.0,), 0.0),
        ((2.0, nan), 0.0),
        ((1.0, inf, 4.0), 3.0),
    ],
)
def test_objective_scale(values, expected) -> None:
    """Check the variation read off the boxes already solved."""
    assert objective_scale(values) == pytest.approx(expected)


def test_probe_starts_at_its_own_rung() -> None:
    """Check that a probe starts at its rung and climbs from there."""
    sweep = ConvexitySweep((1.0, 10.0, 100.0))
    assert sweep.rungs(0) == (1.0, 10.0, 100.0)
    assert sweep.rungs(1) == (10.0, 100.0)
    assert sweep.rungs(2) == (100.0,)
    assert sweep.n_points == 3
    assert sweep.max_value == pytest.approx(100.0)


@pytest.mark.parametrize("index", [-1, 3])
def test_probe_off_the_ladder(index) -> None:
    """Check the error raised for a probe that is not on the ladder."""
    with pytest.raises(IndexError, match=r"probe index must be in \[0, 3\)"):
        ConvexitySweep((1.0, 10.0, 100.0)).rungs(index)


@pytest.mark.parametrize(
    ("ladder", "match"),
    [
        ((), r"ladder of the sweep is empty"),
        ((10.0, 1.0), r"rungs of the ladder must increase"),
        ((1.0, 1.0), r"rungs of the ladder must increase"),
    ],
)
def test_ladder_validation(ladder, match) -> None:
    """Check the errors raised by an unusable sweep."""
    with pytest.raises(ValueError, match=match):
        ConvexitySweep(ladder)


def test_deploy_spans_the_ladder() -> None:
    """Check that an iteration deploys one probe per rung, none escalating."""
    sweep = ConvexitySweep((1.0, 10.0, 100.0))
    deployments = sweep.deploy(lambda value: f"box at {value}")
    assert [one.value for one in deployments] == [1.0, 10.0, 100.0]
    assert [one.index for one in deployments] == [0, 1, 2]
    assert not any(one.escalated for one in deployments)


def test_deploy_redeploys_a_probe_that_proposes_nothing() -> None:
    """Check that a probe proposing nothing new climbs the ladder.

    The bottom rung proposes nothing here, which is the case the sweep exists
    for: a value too small to keep the cuts usable leaves the master with
    nothing to look at, and the probe is not wasted but redeployed higher.
    """
    threshold = 10.0
    sweep = ConvexitySweep((1.0, 10.0, 100.0))
    deployments = sweep.deploy(
        lambda value: f"box at {value}" if value >= threshold else None
    )
    assert [one.value for one in deployments] == [10.0, 100.0]
    assert [one.starting_value for one in deployments] == [1.0, 10.0]
    assert [one.escalated for one in deployments] == [True, True]
    # The probe at the top rung has nowhere to climb, so the last probe of the
    # iteration proposes the box of the rung below it, which is already taken.
    assert [one.index for one in deployments] == [0, 1]


def test_deploy_stops_when_the_ladder_is_exhausted() -> None:
    """Check the stopping criterion: no rung proposes a box not yet solved."""
    values = []

    def solve(value: float) -> None:
        """Propose nothing, whatever the rung.

        Args:
            value: The rung.

        Returns:
            Nothing, ever.
        """
        values.append(value)

    sweep = ConvexitySweep((1.0, 10.0, 100.0))
    assert sweep.deploy(solve) == ()
    # Every probe climbed to the top before giving up.
    assert values == [1.0, 10.0, 100.0, 10.0, 100.0, 100.0]


def test_deploy_counts_a_repeated_proposal_once() -> None:
    """Check that two probes landing on the same box count once."""
    sweep = ConvexitySweep((1.0, 10.0, 100.0))
    deployments = sweep.deploy(lambda value: "the same box")  # noqa: ARG005
    assert len(deployments) == 1
    assert deployments[0].value == pytest.approx(1.0)


def test_sweep_of_an_upper_bound() -> None:
    """Check the sweep built from an upper bound and a number of points."""
    sweep = ConvexitySweepSettings(max_value=100.0, n_points=3).create_sweep()
    assert sweep.ladder == pytest.approx((1.0, 10.0, 100.0))


def test_sweep_read_off_the_objective() -> None:
    """Check the sweep whose upper bound comes from the boxes already solved."""
    settings = ConvexitySweepSettings(n_points=3, headroom=1.0)
    assert settings.create_sweep() is None
    assert settings.create_sweep(
        objective_scale((3.0, 83.0))
    ).max_value == pytest.approx(80.0)


def test_the_headroom_of_an_observed_bound() -> None:
    """Check the factor that lifts an upper bound read off the objective.

    The spread over the boxes already solved is a lower estimate of the spread
    over the design space, and the headroom is what keeps a run whose first
    boxes look alike from never escaping them. It is dimensionless, which is
    what the margin it replaces is not.
    """
    settings = ConvexitySweepSettings(n_points=3, headroom=10.0)
    assert settings.create_sweep(8.0).max_value == pytest.approx(80.0)
    assert settings.create_sweep(0.0) is None


def test_the_headroom_leaves_a_given_bound_alone() -> None:
    """Check that the headroom applies to an observed bound only."""
    settings = ConvexitySweepSettings(max_value=100.0, headroom=10.0)
    assert settings.create_sweep(8.0).max_value == pytest.approx(100.0)


def test_sweep_ignores_the_objective_when_bounded() -> None:
    """Check that a given upper bound wins over the observed one."""
    settings = ConvexitySweepSettings(max_value=100.0, n_points=3)
    assert settings.create_sweep(20.0).max_value == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("max_value", "n_points", "match"),
    [
        (0.0, 4, r"upper bound of the sweep must be positive"),
        (-1.0, 4, r"upper bound of the sweep must be positive"),
        (None, 0, r"number of rungs must be positive"),
    ],
)
def test_sweep_settings_errors(max_value, n_points, match) -> None:
    """Check the errors raised by unusable sweep settings."""
    with pytest.raises(ValueError, match=match):
        ConvexitySweepSettings(max_value=max_value, n_points=n_points)


@pytest.mark.parametrize("headroom", [0.0, -1.0])
def test_headroom_errors(headroom) -> None:
    """Check the error raised by a headroom that is not positive."""
    with pytest.raises(ValueError, match=r"headroom must be positive"):
        ConvexitySweepSettings(headroom=headroom)


@pytest.mark.parametrize(
    ("mechanism", "name"),
    [("adaptive", "min_dfk"), ("convexification", "convexification_constant")],
)
def test_the_setting_the_mechanism_calibrates(mechanism, name) -> None:
    """Check which setting of the master a sweep of the convexity varies."""
    settings = BoxSubdivisionSettings(mechanism=mechanism)
    assert settings.convexity_setting_name == name
    assert settings.convexity_value == settings.to_master_settings()[name]


def test_no_sweep_leaves_the_settings_alone() -> None:
    """Check that the master settings are unchanged without a sweep."""
    settings = BoxSubdivisionSettings(convexity_margin=42.0)
    assert settings.create_convexity_sweep() is None
    assert settings.to_master_settings()["min_dfk"] == pytest.approx(42.0)


def test_a_sweep_degrades_to_its_top_rung() -> None:
    """Check the fallback of a master that does not support the sweep.

    The released master takes one value, so a run that loses the sweep keeps the
    conservative end of the ladder rather than the margin it was going to
    replace: an over-large margin costs sub-problems, not quality.
    """
    settings = BoxSubdivisionSettings(
        convexity_margin=1.0,
        convexity_sweep=ConvexitySweepSettings(max_value=100.0),
    )
    assert settings.create_convexity_sweep().max_value == pytest.approx(100.0)
    assert settings.to_master_settings()["min_dfk"] == pytest.approx(100.0)


def test_a_sweep_of_the_convexification_degrades_too() -> None:
    """Check the same fallback for the other mechanism."""
    settings = BoxSubdivisionSettings(
        mechanism="convexification",
        convexification_constant=1.0,
        convexity_sweep=ConvexitySweepSettings(max_value=50.0),
    )
    master_settings = settings.to_master_settings()
    assert master_settings["convexification_constant"] == pytest.approx(50.0)
    assert master_settings["min_dfk"] == pytest.approx(0.0)


def test_a_sweep_keeps_the_probes_the_convexification_would_drop() -> None:
    """Check that a swept convexification keeps a probe per rung.

    The pure convexification probes a single point on its own, and a sweep of a
    single probe is not a sweep: it is the top rung and nothing else.
    """
    settings = BoxSubdivisionSettings(
        mechanism="convexification",
        n_parallel_points=4,
        convexity_sweep=ConvexitySweepSettings(max_value=50.0),
    )
    assert settings.to_master_settings()["number_of_parallel_points"] == 4
    assert (
        BoxSubdivisionSettings(
            mechanism="convexification", n_parallel_points=4
        ).to_master_settings()["number_of_parallel_points"]
        == 1
    )


def test_an_unbounded_sweep_keeps_the_value_of_the_mechanism() -> None:
    """Check that a sweep reading its bound off the objective has none offline."""
    settings = BoxSubdivisionSettings(
        convexity_margin=42.0, convexity_sweep=ConvexitySweepSettings()
    )
    assert settings.create_convexity_sweep() is None
    assert settings.to_master_settings()["min_dfk"] == pytest.approx(42.0)
