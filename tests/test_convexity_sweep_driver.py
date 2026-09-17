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
from gemseo_box_subdivision._convexity_sweep_driver import _probe
from gemseo_box_subdivision._convexity_sweep_driver import drive_the_sweep


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
    with drive_the_sweep(0.0):
        assert core.OuterApproximationOptimizer._solve_milp is not original

    assert core.OuterApproximationOptimizer._solve_milp is original


def test_the_master_is_restored_after_an_error() -> None:
    """Check that a run raising leaves the master unpatched."""
    original = core.OuterApproximationOptimizer._solve_milp
    with pytest.raises(ValueError, match=r"the run failed"):  # noqa: PT012, SIM117
        with drive_the_sweep(0.0):
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
        with drive_the_sweep(0.0):
            patched = core.OuterApproximationOptimizer._solve_milp
            patched(_Master(), None, None, (3.0, 11.0), *[None] * 12, 1.0)
    finally:
        core.OuterApproximationOptimizer._solve_milp = original

    assert guards, "the master was never solved"
    assert all(guard > 0.0 for guard in guards), guards
