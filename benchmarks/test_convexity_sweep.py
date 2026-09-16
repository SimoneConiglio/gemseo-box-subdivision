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
"""Tests for the stub sweeping the convexity setting of the master."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest
from gemseo_bilevel_outer_approximation.algos.opt.core import (
    outer_approximation_optimizer as core,
)
from numpy import geomspace

from benchmarks.convexity_sweep import _probe_index
from benchmarks.convexity_sweep import parallel_convexity_sweep
from benchmarks.convexity_sweep import run
from benchmarks.problems import PROBLEMS
from gemseo_box_subdivision import ConvexitySweepSettings

N_RUNGS = 4
"""The number of rungs of the ladders under test."""


@dataclass
class FakeMaster:
    """The part of the master that decides which probe is calling."""

    n_parallel_points: int = 4
    current_step: float = 2.0
    min_step: float = 1.0


def test_a_single_probe_takes_the_top_rung() -> None:
    """Check the conservative end for a master with nowhere to spread its probes.

    A lone probe at the bottom rung is a run with its cuts unguarded, which
    converges after two or three boxes and reports success far from the optimum.
    """
    assert _probe_index(FakeMaster(n_parallel_points=1), 2.0, N_RUNGS) == N_RUNGS - 1


def test_the_probe_index_comes_from_the_radius() -> None:
    """Check that each radius of the master maps to its own rung.

    The master does not say which probe is calling, only which trust-region
    radius it was given, out of the ``geomspace(step / 2, step)`` it spreads
    them over. Pairing the two ladders is what makes the tight region and the
    raw cuts explore together.
    """
    master = FakeMaster()
    steps = geomspace(master.current_step / 2, master.current_step, num=4)
    assert [_probe_index(master, step, N_RUNGS) for step in steps] == [0, 1, 2, 3]


def test_more_probes_than_rungs() -> None:
    """Check that the probes spread over a shorter ladder."""
    master = FakeMaster(n_parallel_points=8)
    steps = geomspace(master.current_step / 2, master.current_step, num=8)
    assert [_probe_index(master, step, 2) for step in steps] == [0, 0, 0, 0, 1, 1, 1, 1]


def test_a_call_outside_the_probing_loop() -> None:
    """Check the rung of a call made with the radius of the master itself.

    The master solves its problem outside the probing loop too, to recover from
    an infeasible first iteration, and passes its own radius there. That is the
    top of the ladder, which is the right end for a call looking for any box at
    all.
    """
    assert _probe_index(FakeMaster(), 2.0, N_RUNGS) == N_RUNGS - 1
    assert _probe_index(FakeMaster(), None, N_RUNGS) == N_RUNGS - 1


def test_the_master_is_left_as_it_was() -> None:
    """Check that the stub restores the method it patches."""
    original = core.OuterApproximationOptimizer._solve_milp
    with parallel_convexity_sweep(ConvexitySweepSettings()):
        assert core.OuterApproximationOptimizer._solve_milp is not original

    assert core.OuterApproximationOptimizer._solve_milp is original


def test_the_master_is_restored_after_an_error() -> None:
    """Check that a run raising leaves the master unpatched."""
    original = core.OuterApproximationOptimizer._solve_milp
    with pytest.raises(ValueError, match=r"the run failed"):  # noqa: PT012, SIM117
        with parallel_convexity_sweep(ConvexitySweepSettings()):
            msg = "the run failed"
            raise ValueError(msg)

    assert core.OuterApproximationOptimizer._solve_milp is original


@pytest.mark.parametrize(
    "sweep",
    [ConvexitySweepSettings(max_value=100.0), ConvexitySweepSettings()],
)
def test_a_swept_run_reaches_the_optimum(sweep) -> None:
    """Check that the sweep solves Rastrigin, bounded and unbounded.

    The point of the sweep is that neither of these asks for the margin of
    $100$ the tuning had to find: one is told an upper bound and the other
    reads it off the objective.
    """
    logging.disable(logging.CRITICAL)
    try:
        outcome, trace = run(PROBLEMS["rastrigin"], 11, sweep, 100.0)
    finally:
        logging.disable(logging.NOTSET)

    assert outcome.gap(0.0) == pytest.approx(0.0, abs=1e-3)
    assert trace
    # The redeployment is not decoration: probes do climb above their own rung.
    assert any(one.escalated for one in trace)
