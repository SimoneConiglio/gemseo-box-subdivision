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
"""Tests for the measurement of the convexity sweep, and for the stub driving it.

These pass against either master: one that sweeps the convexity itself, and one
that predates the sweep and is driven from outside.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest
from gemseo_bilevel_outer_approximation.algos.opt.core import (
    outer_approximation_optimizer as core,
)
from numpy import geomspace

from benchmarks.convexity_sweep import MASTER_SWEEPS_CONVEXITY
from benchmarks.convexity_sweep import _probe
from benchmarks.convexity_sweep import convexity_sweep
from benchmarks.convexity_sweep import parallel_convexity_sweep
from benchmarks.convexity_sweep import run
from benchmarks.convexity_sweep import set_headroom
from benchmarks.problems import PROBLEMS
from gemseo_box_subdivision import convexity_sweep as policy


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
    with parallel_convexity_sweep(0.0):
        assert core.OuterApproximationOptimizer._solve_milp is not original

    assert core.OuterApproximationOptimizer._solve_milp is original


def test_the_master_is_restored_after_an_error() -> None:
    """Check that a run raising leaves the master unpatched."""
    original = core.OuterApproximationOptimizer._solve_milp
    with pytest.raises(ValueError, match=r"the run failed"):  # noqa: PT012, SIM117
        with parallel_convexity_sweep(0.0):
            msg = "the run failed"
            raise ValueError(msg)

    assert core.OuterApproximationOptimizer._solve_milp is original


def test_the_headroom_is_set_and_put_back() -> None:
    """Check that the headroom reaches whichever module reads it."""
    original = policy.HEADROOM
    with set_headroom(1.0):
        assert pytest.approx(1.0) == policy.HEADROOM
        if MASTER_SWEEPS_CONVEXITY:
            assert pytest.approx(1.0) == core.HEADROOM

    assert pytest.approx(original) == policy.HEADROOM


def test_no_sweep_asks_for_nothing() -> None:
    """Check that a fixed margin adds no setting and leaves no trace."""
    with convexity_sweep(None) as (settings, trace):
        assert settings == {}
        assert trace == []


def test_the_sweep_goes_to_the_master_that_can_do_it() -> None:
    """Check that the master is asked to sweep, or the stub does it instead."""
    original = core.OuterApproximationOptimizer._solve_milp
    with convexity_sweep(100.0) as (settings, _):
        if MASTER_SWEEPS_CONVEXITY:
            # The rungs are the probes, which the master knows already.
            assert settings == {"convexity_sweep_max": 100.0}
            assert core.OuterApproximationOptimizer._solve_milp is original
        else:
            assert settings == {}
            assert core.OuterApproximationOptimizer._solve_milp is not original


@pytest.mark.parametrize(
    "sweep",
    [100.0, 0.0],
)
def test_a_swept_run_reaches_the_optimum(sweep) -> None:
    """Check that the sweep solves Rastrigin, bounded and unbounded.

    Neither of these is given the margin of $100$ the tuning had to find: one is
    told an upper bound and the other reads it off the objective.
    """
    logging.disable(logging.CRITICAL)
    try:
        outcome, trace = run(PROBLEMS["rastrigin"], 11, sweep, 0.0)
    finally:
        logging.disable(logging.NOTSET)

    assert outcome.gap(0.0) == pytest.approx(0.0, abs=1e-3)
    if not MASTER_SWEEPS_CONVEXITY:
        # The stub keeps a record the master does not, so the redeployment can
        # be seen: probes do climb above their own rung.
        assert trace
        assert any(one.escalated for one in trace)
