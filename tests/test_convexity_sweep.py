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
"""Tests for the settings of a convexity sweep, and for the ladder behind it.

The ladder belongs to the master, so what is tested here is the copy this
package falls back on, which has to behave like the master's, and the two
settings this package turns into the master's own.
"""

from __future__ import annotations

import pytest
from numpy import inf
from numpy import nan

from gemseo_box_subdivision import BoxSubdivisionSettings
from gemseo_box_subdivision import ConvexitySweepSettings
from gemseo_box_subdivision import convexity_sweep as policy
from gemseo_box_subdivision._convexity_sweep_fallback import LADDER_DECADES
from gemseo_box_subdivision._convexity_sweep_fallback import ConvexitySweep
from gemseo_box_subdivision._convexity_sweep_fallback import convexity_ladder
from gemseo_box_subdivision._convexity_sweep_fallback import objective_scale


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


@pytest.mark.parametrize(("index", "expected"), [(-1, 3), (9, 1)])
def test_a_probe_off_the_ladder_is_clamped(index, expected) -> None:
    """Check that a probe with no rung of its own gets one anyway."""
    assert len(ConvexitySweep((1.0, 10.0, 100.0)).rungs(index)) == expected


def test_the_probes_spread_over_the_ladder() -> None:
    """Check that each parallel point of the master gets its own rung."""
    sweep = ConvexitySweep((1.0, 10.0, 100.0))
    assert [sweep.probe_index(3, probe) for probe in range(3)] == [0, 1, 2]


def test_more_probes_than_rungs() -> None:
    """Check that the probes spread over a shorter ladder."""
    sweep = ConvexitySweep((1.0, 100.0))
    assert [sweep.probe_index(4, probe) for probe in range(4)] == [0, 0, 1, 1]


def test_a_lone_probe_takes_the_top_rung() -> None:
    """Check the conservative end for a master with nowhere to spread its probes.

    A lone probe at the bottom rung is a run with its cuts unguarded, which
    converges after two or three boxes and reports success far from the optimum.
    """
    sweep = ConvexitySweep((1.0, 10.0, 100.0))
    assert sweep.rungs(sweep.probe_index(1, 0)) == (100.0,)


def test_the_fallback_matches_the_ladder_in_use() -> None:
    """Check that the ladder in use behaves like the one falling back on it.

    The package prefers the master's copy and carries its own, and the stub of
    the benchmarks drives either, so the two have to agree.
    """
    ladder = (1.0, 10.0, 100.0)
    theirs = policy.ConvexitySweep(ladder)
    ours = ConvexitySweep(ladder)
    assert theirs.ladder == ours.ladder
    assert theirs.max_value == pytest.approx(ours.max_value)
    assert [theirs.rungs(index) for index in range(3)] == [
        ours.rungs(index) for index in range(3)
    ]
    assert [theirs.probe_index(4, probe) for probe in range(4)] == [
        ours.probe_index(4, probe) for probe in range(4)
    ]
    assert policy.convexity_ladder(100.0, 4) == pytest.approx(
        convexity_ladder(100.0, 4)
    )
    assert policy.objective_scale((1.0, 9.0)) == pytest.approx(
        objective_scale((1.0, 9.0))
    )


def test_sweep_of_an_upper_bound() -> None:
    """Check the ladder built from an upper bound and a number of points."""
    sweep = ConvexitySweepSettings(max_value=100.0, n_points=3).create_sweep()
    assert sweep.ladder == pytest.approx((1.0, 10.0, 100.0))


def test_sweep_read_off_the_objective() -> None:
    """Check the ladder whose bound comes from the boxes already solved.

    That spread is a lower estimate of the spread over the design space, so the
    bound is the spread lifted by the headroom.
    """
    settings = ConvexitySweepSettings(n_points=3)
    assert settings.create_sweep() is None
    assert settings.create_sweep(objective_scale((3.0, 11.0))).max_value == (
        pytest.approx(8.0 * policy.HEADROOM)
    )


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


def test_the_settings_asked_of_a_master_that_sweeps(monkeypatch) -> None:
    """Check the two settings a sweep becomes."""
    monkeypatch.setattr(policy, "MASTER_SWEEPS_CONVEXITY", True)
    assert ConvexitySweepSettings(max_value=100.0, n_points=3).to_master_settings() == {
        "convexity_sweep_points": 3,
        "convexity_sweep_max": 100.0,
    }
    # An upper bound left unset is a bound of zero, which is what asks the
    # master to read one off the objective.
    assert ConvexitySweepSettings(n_points=3).to_master_settings() == {
        "convexity_sweep_points": 3,
        "convexity_sweep_max": 0.0,
    }


def test_nothing_is_asked_of_a_master_that_does_not_sweep(monkeypatch) -> None:
    """Check that a master predating the sweep is sent no setting it rejects."""
    monkeypatch.setattr(policy, "MASTER_SWEEPS_CONVEXITY", False)
    assert ConvexitySweepSettings(max_value=100.0).to_master_settings() == {}


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
    master_settings = settings.to_master_settings()
    assert master_settings["min_dfk"] == pytest.approx(42.0)
    assert "convexity_sweep_points" not in master_settings


def test_a_sweep_reaches_the_master(monkeypatch) -> None:
    """Check that a sweep is passed on, with the top rung for the iterations
    before the master has a ladder of its own.
    """  # noqa: D205
    monkeypatch.setattr(policy, "MASTER_SWEEPS_CONVEXITY", True)
    settings = BoxSubdivisionSettings(
        convexity_margin=1.0,
        convexity_sweep=ConvexitySweepSettings(max_value=100.0, n_points=3),
    )
    master_settings = settings.to_master_settings()
    assert master_settings["convexity_sweep_points"] == 3
    assert master_settings["convexity_sweep_max"] == pytest.approx(100.0)
    assert master_settings["min_dfk"] == pytest.approx(100.0)


def test_a_sweep_degrades_to_its_top_rung(monkeypatch) -> None:
    """Check the fallback of a master that does not sweep.

    Such a master takes one value, so a run that loses the sweep keeps the
    conservative end of the ladder rather than the margin it was going to
    replace: an over-large margin costs sub-problems, not quality.
    """
    monkeypatch.setattr(policy, "MASTER_SWEEPS_CONVEXITY", False)
    settings = BoxSubdivisionSettings(
        convexity_margin=1.0,
        convexity_sweep=ConvexitySweepSettings(max_value=100.0),
    )
    master_settings = settings.to_master_settings()
    assert master_settings["min_dfk"] == pytest.approx(100.0)
    assert "convexity_sweep_points" not in master_settings


def test_a_sweep_of_the_convexification_degrades_too(monkeypatch) -> None:
    """Check the same fallback for the other mechanism."""
    monkeypatch.setattr(policy, "MASTER_SWEEPS_CONVEXITY", False)
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
