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
"""Tests of the driver sweeping the convexity from outside the master.

The sweep belongs to the master, and the released one does not implement it, so
the package drives the ladder around its mixed-integer solve instead. These tests
live here rather than beside the benchmark because the driver is library code: an
unbounded sweep would otherwise run with no convexity at all, the master's own
default being zero.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from gemseo_bilevel_outer_approximation.algos.opt.core import (
    outer_approximation_optimizer as core,
)
from numpy import geomspace
from numpy import zeros

from gemseo_box_subdivision import SweptBoxSubdivisionSettings
from gemseo_box_subdivision._convexity_sweep_driver import _DELEGATE
from gemseo_box_subdivision._convexity_sweep_driver import _probe
from gemseo_box_subdivision._convexity_sweep_driver import drive_the_sweep
from gemseo_box_subdivision._convexity_sweep_fallback import ConvexitySweep


@dataclass
class FakeMaster:
    """The part of the master that says which probe is calling."""

    n_parallel_points: int = 4
    current_step: float = 2.0
    min_step: float = 1.0


def test_the_probe_comes_from_the_radius() -> None:
    """Check that each radius of the master maps to its own probe.

    The master does not say which probe is calling, only which trust-region
    radius it was given, out of the ``geomspace(step / 2, step)`` it spreads
    them over.
    """
    master = FakeMaster()
    steps = geomspace(master.current_step / 2, master.current_step, num=4)
    assert [_probe(master, step) for step in steps] == [0, 1, 2, 3]


def test_a_single_probe() -> None:
    """Check the probe of a master that runs only one."""
    assert _probe(FakeMaster(n_parallel_points=1), 2.0) == 0


def test_a_solve_outside_the_probing_loop() -> None:
    """Check the probe of a solve made with the radius of the master itself.

    The master solves outside the probing loop too, to recover from an
    infeasible first iteration, and passes its own radius there. That is the top
    of the radius ladder, hence the last probe, whose rung is the conservative
    end.
    """
    assert _probe(FakeMaster(), 2.0) == 3
    assert _probe(FakeMaster(), None) == 3


def test_the_master_is_left_as_it_was() -> None:
    """Check that the stub restores the method it patches."""
    original = core.OuterApproximationOptimizer._solve_milp
    with drive_the_sweep(SweptBoxSubdivisionSettings()):
        assert core.OuterApproximationOptimizer._solve_milp is not original

    assert core.OuterApproximationOptimizer._solve_milp is original


def test_the_master_is_restored_after_an_error() -> None:
    """Check that a run raising leaves the master unpatched."""
    original = core.OuterApproximationOptimizer._solve_milp
    with pytest.raises(ValueError, match=r"the run failed"):  # noqa: PT012, SIM117
        with drive_the_sweep(SweptBoxSubdivisionSettings()):
            msg = "the run failed"
            raise ValueError(msg)

    assert core.OuterApproximationOptimizer._solve_milp is original


def test_the_settings_drive_the_master_that_cannot_sweep() -> None:
    """Check that a swept run patches the master where the master has no sweep.

    This is what makes the unbounded form work at all: the bound is the spread of
    the objective, which only something watching the run can compute, and the
    master's own default convexity is zero.
    """
    original = core.OuterApproximationOptimizer._solve_milp
    with SweptBoxSubdivisionSettings().drive_the_master():
        assert core.OuterApproximationOptimizer._solve_milp is not original

    assert core.OuterApproximationOptimizer._solve_milp is original


def test_the_general_settings_drive_nothing() -> None:
    """Check that a calibrated run leaves the master alone."""
    from gemseo_box_subdivision import BoxSubdivisionSettings

    original = core.OuterApproximationOptimizer._solve_milp
    with BoxSubdivisionSettings().drive_the_master():
        assert core.OuterApproximationOptimizer._solve_milp is original


def test_the_ladder_a_probe_is_given_is_computed_from_the_objective() -> None:
    """Check that a probe is given a rung of the ladder, not a guard of zero.

    The objective history reaches the driver as the master's own argument, and
    the bound follows its spread with the headroom, so every solve after the
    first two boxes is guarded by a real value.
    """
    guards = []

    class _Master:
        n_parallel_points = 4
        current_step = 2.0
        min_step = 1.0
        min_dfk = 0.0

        def _is_previously_computed(self, alpha) -> bool:  # noqa: ANN001
            return False

    def _solve(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        guards.append(self.min_dfk)
        return zeros((1, 1)), None, True

    original = core.OuterApproximationOptimizer._solve_milp
    core.OuterApproximationOptimizer._solve_milp = _solve
    try:
        with drive_the_sweep(SweptBoxSubdivisionSettings()):
            patched = core.OuterApproximationOptimizer._solve_milp
            # Fifteen arguments, as the master passes them: the objective
            # history third and the radius of the probe last.
            patched(_Master(), None, None, (3.0, 11.0), *[None] * 11, 1.0)
    finally:
        core.OuterApproximationOptimizer._solve_milp = original

    assert guards, "the master was never solved"
    assert all(guard > 0.0 for guard in guards), guards


def test_a_probe_on_the_floor_of_the_trust_region_takes_the_top_rung() -> None:
    """Check the rung of a probe the master cannot distinguish.

    The master decreases its radius as it goes, and once the radius reaches its
    floor every probe is given the same one: ``geomspace`` then spans nothing and
    the probes are indistinguishable. They belong at the conservative end, as a
    lone probe does, and not at the bottom rung, which is where the nearest-radius
    rule would otherwise put every one of them.
    """
    on_the_floor = FakeMaster(current_step=1.0, min_step=1.0)
    assert [_probe(on_the_floor, 1.0) for _ in range(4)] == [3, 3, 3, 3]

    # While the region still spans something, the probes still spread over it.
    spread = FakeMaster()
    radii = geomspace(spread.current_step / 2, spread.current_step, num=4)
    assert [_probe(spread, float(radius)) for radius in radii] == [0, 1, 2, 3]


def test_the_boxes_found_infeasible_carry_a_scale_too() -> None:
    """Check that the bound is read off every box solved, not the feasible ones.

    A problem whose first boxes are infeasible has objective values all the same,
    so the feasible history alone gives no spread and the master would keep
    solving at its own convexity, which is zero. The infeasible history is the
    same measurement of the same objective.
    """
    guards = []

    class _Master:
        n_parallel_points = 4
        current_step = 2.0
        min_step = 1.0
        min_dfk = 0.0

        def _is_previously_computed(self, alpha) -> bool:  # noqa: ANN001
            return False

    def _solve(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        guards.append(self.min_dfk)
        return zeros((1, 1)), None, True

    original = core.OuterApproximationOptimizer._solve_milp
    core.OuterApproximationOptimizer._solve_milp = _solve
    try:
        with drive_the_sweep(SweptBoxSubdivisionSettings()):
            patched = core.OuterApproximationOptimizer._solve_milp
            # One feasible box, so no spread of its own, and two infeasible ones.
            # Fifteen arguments: the feasible history third, the infeasible one
            # thirteenth and the radius of the probe last.
            patched(
                _Master(),
                None,
                None,
                (3.0,),
                *[None] * 9,
                (7.0, 11.0),
                None,
                2.0,
            )
    finally:
        core.OuterApproximationOptimizer._solve_milp = original

    assert guards, "the master was never solved"
    assert all(guard > 0.0 for guard in guards), guards


def test_the_master_is_driven_whichever_way_the_scenario_is_executed() -> None:
    """Check that settings given to ``execute`` do not bypass the driving.

    A caller overriding a setting of the master still needs the sweep: what the
    run supplies its master is not one of the settings the caller is overriding,
    and a swept run reaching the master without it solves at a convexity of zero.
    The benchmark harness takes exactly this path, passing a settings model.
    """
    from gemseo import create_design_space
    from gemseo import create_discipline
    from gemseo_bilevel_outer_approximation.algos.opt.bilevel_master_outer_approximation.bilevel_master_outer_approximation_settings import (  # noqa: E501
        BiLevelMasterOuterApproximation_Settings,
    )
    from numpy import array

    from gemseo_box_subdivision import BoxSubdivisionScenario

    guards = []
    gates = []
    original = core.OuterApproximationOptimizer._solve_milp

    def spy(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        guards.append(self.min_dfk)
        gates.append(self.use_adaptative_convexification)
        return original(self, *args, **kwargs)

    discipline = create_discipline(
        "AnalyticDiscipline",
        expressions={"f": "10*(x**2 - 10*cos(6.28*x)) + 10*(y**2 - 10*cos(6.28*y))"},
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
        n_subdivisions=5,
        settings=SweptBoxSubdivisionSettings(),
    )

    core.OuterApproximationOptimizer._solve_milp = spy
    try:
        # The path a caller takes when it configures the master itself.
        scenario.execute(BiLevelMasterOuterApproximation_Settings(max_iter=4))
    finally:
        core.OuterApproximationOptimizer._solve_milp = original

    assert guards, "the master was never solved"
    assert any(guard > 0.0 for guard in guards), (
        "every solve ran at the master's own convexity, so the sweep was skipped"
    )

    # Setting the margin is not guarding the cuts with it: the master reads the
    # margin only behind its own switch, and a settings model that says nothing
    # of the mechanism leaves that switch off. A swept run that sets a margin the
    # master never reads is the unguarded run, dressed as a swept one.
    assert all(gates), (
        "the master ran with the adaptive repair off, so it read no margin at all"
    )


def test_the_probes_of_the_master_are_the_rungs_it_gets() -> None:
    """Check that the ladder follows the probes the master actually runs.

    The rungs are the probes, and a caller configuring the master is the one
    saying how many there are, so the ladder has to be built from what the master
    ended up with rather than from what the settings would have asked for.
    """
    built = []

    @dataclass
    class _Master:
        """A master running a number of probes of its own choosing."""

        n_parallel_points: int
        min_step: float = 1.0
        current_step: float = 2.0
        min_dfk: float = 0.0

        def _is_previously_computed(self, alpha) -> bool:  # noqa: ANN001
            return False

    def _solve(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        built.append(self.min_dfk)
        return zeros((1, 1)), None, True

    original = core.OuterApproximationOptimizer._solve_milp
    core.OuterApproximationOptimizer._solve_milp = _solve
    try:
        # The settings would ask a master for four probes; this one runs six, so
        # the ladder spans six rungs over the two decades below the bound.
        with drive_the_sweep(SweptBoxSubdivisionSettings(max_value=100.0)):
            patched = core.OuterApproximationOptimizer._solve_milp
            master = _Master(6)
            for radius in geomspace(1.0, 2.0, 6):
                patched(master, None, None, (3.0, 11.0), *[None] * 11, float(radius))
    finally:
        core.OuterApproximationOptimizer._solve_milp = original

    # Six rungs over the two decades below the bound, one per probe. A ladder
    # built from the four probes the settings would have asked for would agree
    # at the ends and nowhere else, so the middle is what pins it.
    six_rungs = ConvexitySweep.from_bounds(100.0, 6).ladder
    assert built == [pytest.approx(rung) for rung in six_rungs], built


def test_a_context_left_out_of_order_leaves_the_master_as_it_found_it() -> None:
    """Check that leaving two contexts in either order ends with no patch left.

    Nesting is the ordinary case and unwinds exactly. Where two are left in the
    order they were entered instead, the one still open must keep its patch, or
    its run finishes unswept; and the one that left must stop driving, or the
    master keeps a wrapper whose context has ended, for the rest of the process.
    """
    original = core.OuterApproximationOptimizer._solve_milp

    outer = drive_the_sweep(SweptBoxSubdivisionSettings(max_value=10.0))
    inner = drive_the_sweep(SweptBoxSubdivisionSettings(max_value=20.0))
    outer.__enter__()
    outer_patch = core.OuterApproximationOptimizer._solve_milp
    inner.__enter__()
    still_driving = core.OuterApproximationOptimizer._solve_milp

    outer.__exit__(None, None, None)
    assert core.OuterApproximationOptimizer._solve_milp is still_driving

    # The context that left is out of the chain, so the one still open no longer
    # solves through it: it solves through what the master had to begin with.
    assert getattr(still_driving, _DELEGATE) is not outer_patch
    assert getattr(still_driving, _DELEGATE) is original

    inner.__exit__(None, None, None)
    assert core.OuterApproximationOptimizer._solve_milp is original

    # Nesting, which is how a benchmark inside a scenario meets one, unwinds to
    # exactly what was there before.
    with (
        drive_the_sweep(SweptBoxSubdivisionSettings(max_value=10.0)),
        drive_the_sweep(SweptBoxSubdivisionSettings(max_value=20.0)),
    ):
        pass

    assert core.OuterApproximationOptimizer._solve_milp is original


def test_a_sweep_buried_under_a_foreign_patch_stops_when_its_context_ends() -> None:
    """Check that a sweep no longer reachable by name stops sweeping anyway.

    A wrapper this module did not install, the trust-region benchmark's among
    them, says nothing of what it delegates to, so it cannot be spliced and the
    sweep stays in the chain when its context ends. It must then do nothing: a
    run after the context is not a swept run, and guarding its cuts with a ladder
    nobody asked for is as silent as guarding them with none.
    """
    guards = []

    class _Master:
        n_parallel_points = 4
        current_step = 2.0
        min_step = 1.0
        min_dfk = 0.0

        def _is_previously_computed(self, alpha) -> bool:  # noqa: ANN001
            return False

    def _solve(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        guards.append(self.min_dfk)
        return zeros((1, 1)), None, True

    original = core.OuterApproximationOptimizer._solve_milp
    core.OuterApproximationOptimizer._solve_milp = _solve
    try:
        with drive_the_sweep(SweptBoxSubdivisionSettings()):
            driving = core.OuterApproximationOptimizer._solve_milp

            def foreign(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
                return driving(self, *args, **kwargs)

            core.OuterApproximationOptimizer._solve_milp = foreign

        # The foreign wrapper says nothing of what it wraps, so the sweep could
        # not be taken out of the chain and is still reached through it.
        assert core.OuterApproximationOptimizer._solve_milp is foreign

        foreign(_Master(), None, None, (3.0, 11.0), *[None] * 11, 1.0)
    finally:
        core.OuterApproximationOptimizer._solve_milp = original

    assert guards, "the master was never solved"
    assert guards == [0.0], (
        "a context that has ended still swept the convexity of a later solve"
    )


def test_the_sweep_entered_inside_another_is_the_one_that_drives() -> None:
    """Check that two open contexts do not both set a rung on one solve.

    The inner context is the run's: it was entered for the run being solved. Both
    wrappers sit in the chain, so the outer one would set its own rung after the
    inner one set its, and the master would solve at the outer value while the
    trace named the inner rung.
    """
    guards = []

    class _Master:
        n_parallel_points = 4
        current_step = 2.0
        min_step = 1.0
        min_dfk = 0.0

        def _is_previously_computed(self, alpha) -> bool:  # noqa: ANN001
            return False

    def _solve(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        guards.append(self.min_dfk)
        return zeros((1, 1)), None, True

    original = core.OuterApproximationOptimizer._solve_milp
    core.OuterApproximationOptimizer._solve_milp = _solve
    try:
        with (
            drive_the_sweep(SweptBoxSubdivisionSettings(max_value=1000.0)),
            drive_the_sweep(SweptBoxSubdivisionSettings(max_value=10.0)) as trace,
        ):
            patched = core.OuterApproximationOptimizer._solve_milp
            patched(_Master(), None, None, (3.0, 11.0), *[None] * 11, 1.0)
    finally:
        core.OuterApproximationOptimizer._solve_milp = original

    # One solve, at one rung: of the inner ladder, which tops out at ten, and not
    # of the outer one, which tops out at a thousand.
    assert guards == [pytest.approx(ConvexitySweep.from_bounds(10.0, 4).ladder[0])]
    assert trace, "the solve proposed nothing, so no rung was reported"
    assert trace[0].value == pytest.approx(guards[0])


def test_the_mechanism_not_swept_is_switched_off_on_the_master() -> None:
    """Check that driving one mechanism leaves the other one off.

    The two are never combined, and a run that configured its own master may have
    both live: the adaptive repair is on by default in the benchmark harness, so
    a swept convexification would be repaired as well, which is neither of the
    two configurations the method is measured in.
    """
    seen = []

    class _Master:
        n_parallel_points = 4
        current_step = 2.0
        min_step = 1.0
        min_dfk = 7.0
        convexification_constant = 0.0
        use_adaptative_convexification = True

        def _is_previously_computed(self, alpha) -> bool:  # noqa: ANN001
            return False

    def _solve(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        seen.append((
            self.min_dfk,
            self.convexification_constant,
            self.use_adaptative_convexification,
        ))
        return zeros((1, 1)), None, True

    original = core.OuterApproximationOptimizer._solve_milp
    core.OuterApproximationOptimizer._solve_milp = _solve
    try:
        settings = SweptBoxSubdivisionSettings(
            mechanism="convexification", max_value=10.0
        )
        with drive_the_sweep(settings):
            patched = core.OuterApproximationOptimizer._solve_milp
            patched(_Master(), None, None, (3.0, 11.0), *[None] * 11, 1.0)
    finally:
        core.OuterApproximationOptimizer._solve_milp = original

    assert seen, "the master was never solved"
    for margin, constant, adapting in seen:
        assert constant > 0.0, "the mechanism being swept was not deployed"
        assert not adapting, "the master repaired its cuts as well as convexified"
        assert margin == pytest.approx(0.0), (
            "the margin of the repair was left standing"
        )
