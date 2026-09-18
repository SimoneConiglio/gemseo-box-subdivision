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
from pydantic import create_model

from gemseo_box_subdivision import BoxSubdivisionSettings
from gemseo_box_subdivision import SweptBoxSubdivisionSettings
from gemseo_box_subdivision import convexity_sweep as policy
from gemseo_box_subdivision import settings as settings_module
from gemseo_box_subdivision._convexity_sweep_fallback import LADDER_DECADES
from gemseo_box_subdivision._convexity_sweep_fallback import ConvexitySweep
from gemseo_box_subdivision._convexity_sweep_fallback import convexity_ladder
from gemseo_box_subdivision._convexity_sweep_fallback import objective_scale
from gemseo_box_subdivision.settings import MASTER_ALGO_NAME


def test_ladder_ends_at_the_upper_bound() -> None:
    """Check that the ladder spans its decades and ends at the upper bound."""
    ladder = convexity_ladder(100.0, 4)
    assert ladder[-1] == pytest.approx(100.0)
    assert ladder[0] == pytest.approx(100.0 / 10.0**LADDER_DECADES)
    assert list(ladder) == sorted(ladder)


def test_ladder_of_a_single_point() -> None:
    """Check that a single point is the value it would replace."""
    assert convexity_ladder(80.0, 1) == (80.0,)
    # One rung spans nothing by construction, so a span of zero is not its
    # business and is not refused.
    assert convexity_ladder(80.0, 1, decades=0.0) == (80.0,)


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
        # A span of zero puts every rung on the upper bound, which the sweep
        # itself then refuses as not increasing: the ladder is what says why.
        (10.0, 4, 0.0, r"more than one rung must be positive"),
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


def test_the_ladder_of_a_bound_and_a_count() -> None:
    """Check the ladder built from an upper bound and a number of rungs."""
    assert ConvexitySweep.from_bounds(100.0, 3).ladder == pytest.approx((
        1.0,
        10.0,
        100.0,
    ))


def test_the_bound_read_off_the_objective() -> None:
    """Check the bound taken from the boxes already solved.

    That spread is a lower estimate of the spread over the design space, so the
    bound is the spread lifted by the headroom.
    """
    bound = objective_scale((3.0, 11.0)) * policy.HEADROOM
    assert bound == pytest.approx(8.0 * policy.HEADROOM)
    assert ConvexitySweep.from_bounds(bound, 3).max_value == pytest.approx(bound)


def _install_a_sweeping_master(monkeypatch) -> None:
    """Make the master of the settings a master that sweeps the convexity.

    Two things say whether the installed master sweeps, and a simulated one has
    to say both: :data:`.MASTER_SWEEPS_CONVEXITY`, which decides whether the
    settings are passed at all, and the settings the master declares, against
    which they are checked when the settings are built. The released master has
    neither, so patching the flag alone would ask it for settings it does not
    take.
    """
    monkeypatch.setattr(policy, "MASTER_SWEEPS_CONVEXITY", True)
    monkeypatch.setattr(settings_module, "MASTER_SWEEPS_CONVEXITY", True)

    master_settings_class = create_model(
        "SweepingMaster_Settings",
        __base__=settings_module._get_settings_class(MASTER_ALGO_NAME),
        convexity_sweep_points=(int, 0),
        convexity_sweep_max=(float, 0.0),
    )
    get_settings_class = settings_module._get_settings_class

    def _get_settings_class(algo_name: str):
        if algo_name == MASTER_ALGO_NAME:
            return master_settings_class

        return get_settings_class(algo_name)

    monkeypatch.setattr(settings_module, "_get_settings_class", _get_settings_class)


def test_the_general_settings_do_not_sweep() -> None:
    """Check that the general construction asks for no sweep at all.

    Sweeping and calibrating are the two entry points, and the general one is
    the calibrated one: there is no sweep to ask it for.
    """
    master_settings = BoxSubdivisionSettings(convexity_margin=42.0).to_master_settings()
    assert master_settings["min_dfk"] == pytest.approx(42.0)
    assert "convexity_sweep_points" not in master_settings
    assert not hasattr(BoxSubdivisionSettings(), "max_value")


def test_a_sweep_reaches_the_master(monkeypatch) -> None:
    """Check that a sweep is passed on, with the top rung for the iterations
    before the master has a ladder of its own.
    """  # noqa: D205
    _install_a_sweeping_master(monkeypatch)
    settings = SweptBoxSubdivisionSettings(max_value=100.0, n_parallel_points=3)
    master_settings = settings.to_master_settings()
    assert master_settings["convexity_sweep_points"] == 3
    assert master_settings["convexity_sweep_max"] == pytest.approx(100.0)
    assert master_settings["min_dfk"] == pytest.approx(100.0)


def test_the_rungs_are_the_probes(monkeypatch) -> None:
    """Check that one number is the probes and the rungs, at any count.

    A probe per rung is the whole construction, so the two cannot disagree: they
    are not two settings that happen to share a default.
    """
    _install_a_sweeping_master(monkeypatch)
    for n_points in (1, 2, 4, 8):
        settings = SweptBoxSubdivisionSettings(
            max_value=100.0, n_parallel_points=n_points
        )
        master_settings = settings.to_master_settings()
        assert master_settings["number_of_parallel_points"] == n_points
        assert master_settings["convexity_sweep_points"] == n_points
        assert len(settings.create_sweep().ladder) == n_points


def _install_a_master_that_does_not_sweep(monkeypatch) -> None:
    """Make the installed master one predating the sweep.

    Both modules have to say so: :mod:`~gemseo_box_subdivision.settings` imported
    the flag at module scope, so it reads its own binding and not the one of
    :mod:`~gemseo_box_subdivision.convexity_sweep`. Patching the latter alone
    leaves the settings reading whatever the installed master happens to give,
    which is what a test of the fallback must not depend on.
    """
    monkeypatch.setattr(policy, "MASTER_SWEEPS_CONVEXITY", False)
    monkeypatch.setattr(settings_module, "MASTER_SWEEPS_CONVEXITY", False)


def test_a_sweep_degrades_to_its_top_rung(monkeypatch) -> None:
    """Check the fallback of a master that does not sweep.

    Such a master takes one value, so a run that loses the sweep keeps the
    conservative end of the ladder rather than the margin it was going to
    replace: an over-large margin costs sub-problems, not quality.
    """
    _install_a_master_that_does_not_sweep(monkeypatch)
    master_settings = SweptBoxSubdivisionSettings(max_value=100.0).to_master_settings()
    assert master_settings["min_dfk"] == pytest.approx(100.0)
    assert "convexity_sweep_points" not in master_settings


def test_a_sweep_of_the_convexification_degrades_too(monkeypatch) -> None:
    """Check the same fallback for the other mechanism."""
    _install_a_master_that_does_not_sweep(monkeypatch)
    master_settings = SweptBoxSubdivisionSettings(
        mechanism="convexification", max_value=50.0
    ).to_master_settings()
    assert master_settings["convexification_constant"] == pytest.approx(50.0)
    assert master_settings["min_dfk"] == pytest.approx(0.0)


def test_a_sweep_keeps_the_probes_the_convexification_would_drop() -> None:
    """Check that a swept convexification keeps a probe per rung.

    The pure convexification probes a single point on its own, and a sweep of a
    single probe is not a sweep: it is the top rung and nothing else.
    """
    swept = SweptBoxSubdivisionSettings(
        mechanism="convexification", n_parallel_points=4, max_value=50.0
    )
    assert swept.to_master_settings()["number_of_parallel_points"] == 4
    assert (
        BoxSubdivisionSettings(
            mechanism="convexification", n_parallel_points=4
        ).to_master_settings()["number_of_parallel_points"]
        == 1
    )


def test_an_unbounded_sweep_computes_its_bound() -> None:
    """Check that a sweep given no bound reads one off the objective.

    That is the form the method exists for: the user supplies nothing, and the
    bound follows the spread of the objective over the boxes already solved,
    lifted by the headroom, since the spread is a lower estimate of the spread
    over the design space.
    """
    settings = SweptBoxSubdivisionSettings()
    assert settings.create_sweep() is None, "nothing solved yet, so nothing to read"

    sweep = settings.create_sweep(objective_scale((3.0, 11.0)))
    assert sweep.max_value == pytest.approx(8.0 * policy.HEADROOM)
    assert len(sweep.ladder) == settings.n_parallel_points


def test_an_unbounded_sweep_leaves_the_master_its_own_value() -> None:
    """Check that an unknown bound is not sent to the master as a guard of zero.

    Before anything is solved there is no value to give, and a margin of zero is
    not "no value": it is a run with its cuts unguarded, which converges after
    two or three boxes and reports success far from the optimum. The master keeps
    what it uses by default until the bound can be computed.
    """
    master_settings = SweptBoxSubdivisionSettings().to_master_settings()
    assert "min_dfk" not in master_settings
    # The other mechanism is still switched off, so the two are never both live.
    assert master_settings["convexification_constant"] == pytest.approx(0.0)

    swept = SweptBoxSubdivisionSettings(mechanism="convexification")
    master_settings = swept.to_master_settings()
    assert "convexification_constant" not in master_settings
    assert master_settings["min_dfk"] == pytest.approx(0.0)


def test_a_bounded_sweep_gives_the_master_its_top_rung() -> None:
    """Check that a bound, unlike no bound, is a value the master can be given."""
    assert SweptBoxSubdivisionSettings(max_value=100.0).to_master_settings()[
        "min_dfk"
    ] == pytest.approx(100.0)


def test_an_unbounded_sweep_asks_the_master_for_the_bound(monkeypatch) -> None:
    """Check that a sweeping master is told to read the bound off the objective.

    A bound of zero is what asks it to, which is the same instruction the
    unbounded form gives the stub driving an older master.
    """
    _install_a_sweeping_master(monkeypatch)
    master_settings = SweptBoxSubdivisionSettings().to_master_settings()
    assert master_settings["convexity_sweep_max"] == pytest.approx(0.0)
    assert master_settings["convexity_sweep_points"] == 4


def test_the_sweep_survives_a_caller_configuring_a_sweeping_master(monkeypatch) -> None:
    """Check what a run keeps of its master settings whatever a caller passes.

    A caller giving the master its own settings takes the path that skips
    :meth:`.to_master_settings` entirely, so a sweeping master would be sent no
    sweep at all and would solve at its own convexity, which is zero. The sweep
    is what the swept entry point is, so it is what the run keeps.
    """
    settings = SweptBoxSubdivisionSettings(max_value=100.0, n_parallel_points=6)
    # A master that does not sweep needs nothing passed: the driver applies the
    # ladder around its solves instead.
    _install_a_master_that_does_not_sweep(monkeypatch)
    assert settings.master_settings_the_run_needs() == {}

    _install_a_sweeping_master(monkeypatch)
    assert settings.master_settings_the_run_needs() == {
        "convexity_sweep_points": 6,
        "convexity_sweep_max": pytest.approx(100.0),
    }


def test_the_general_construction_keeps_nothing_of_its_master_settings() -> None:
    """Check that a caller configuring the master of a calibrated run owns it.

    The general construction names its master and passes it whatever it takes,
    so a caller overriding those settings is choosing what the master is given,
    the convexity included: there is nothing the run needs behind its back.
    """
    assert (
        BoxSubdivisionSettings(convexity_margin=42.0).master_settings_the_run_needs()
        == {}
    )


def test_a_caller_s_settings_carry_what_the_run_needs() -> None:
    """Check that the needed settings are set on a copy of the caller's model."""
    from gemseo_box_subdivision.scenario import _keeping

    model_class = create_model(
        "Sweeping_Settings",
        convexity_sweep_points=(int, 0),
        convexity_sweep_max=(float, 0.0),
    )
    model = model_class()
    kept = _keeping(model, {"convexity_sweep_points": 6, "convexity_sweep_max": 100.0})

    assert kept.convexity_sweep_points == 6
    assert kept.convexity_sweep_max == pytest.approx(100.0)
    # The model is the caller's, and a caller reusing it for another run is not
    # configuring this one.
    assert model.convexity_sweep_points == 0


def test_a_master_that_cannot_do_what_the_run_needs_is_refused() -> None:
    """Check that settings without room for the sweep are refused, not ignored.

    Running anyway is a swept run solving at a convexity of zero, and saying so
    where the settings are given is the whole of the difference.
    """
    from gemseo_box_subdivision.scenario import _keeping

    model = create_model("Plain_Settings", max_iter=(int, 10))()
    with pytest.raises(ValueError, match=r"do not declare \['convexity_sweep_max'\]"):
        _keeping(model, {"convexity_sweep_max": 100.0})


def test_a_swept_scenario_will_not_run_a_master_it_cannot_sweep(monkeypatch) -> None:
    """Check that the refusal reaches the caller through ``execute``.

    The wiring is what the guarantee rests on: a swept run executed with settings
    of the caller's own must still reach its master with the sweep, and where
    those settings have no room for it, must say so rather than run unswept.
    """
    from gemseo import create_design_space
    from gemseo import create_discipline
    from gemseo_bilevel_outer_approximation.algos.opt.bilevel_master_outer_approximation.bilevel_master_outer_approximation_settings import (  # noqa: E501
        BiLevelMasterOuterApproximation_Settings,
    )
    from numpy import array

    from gemseo_box_subdivision import BoxSubdivisionScenario

    discipline = create_discipline(
        "AnalyticDiscipline", expressions={"f": "x**2 + y**2"}
    )
    design_space = create_design_space()
    design_space.add_variable(
        "x", lower_bound=-2.0, upper_bound=2.0, value=array([1.3])
    )
    design_space.add_variable(
        "y", lower_bound=-2.0, upper_bound=2.0, value=array([0.7])
    )
    scenario = BoxSubdivisionScenario(
        [discipline],
        "f",
        design_space,
        n_subdivisions=2,
        settings=SweptBoxSubdivisionSettings(),
    )

    _install_a_sweeping_master(monkeypatch)
    with pytest.raises(ValueError, match=r"which this run needs of it"):
        scenario.execute(BiLevelMasterOuterApproximation_Settings(max_iter=2))
