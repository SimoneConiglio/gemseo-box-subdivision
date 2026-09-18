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
from importlib import import_module

import pytest
from gemseo_bilevel_outer_approximation.algos.opt.core import (
    outer_approximation_optimizer as core,
)

from benchmarks.configurations import ADAPTIVE
from benchmarks.convexity_sweep import MASTER_SWEEPS_CONVEXITY
from benchmarks.convexity_sweep import convexity_sweep
from benchmarks.convexity_sweep import run
from benchmarks.convexity_sweep import set_headroom
from benchmarks.problems import PROBLEMS
from gemseo_box_subdivision import convexity_sweep as policy
from gemseo_box_subdivision.convexity_sweep import objective_scale


def test_the_headroom_is_set_and_put_back() -> None:
    """Check that the headroom reaches whichever module reads it.

    A constant is read through a binding, and it has one per module importing
    it: the one re-exporting it, which this package's settings read, the one
    defining it, which is the master's own where the master sweeps and this
    package's fallback where it does not, and the module solving, where a
    sweeping master imported it. Leaving any of them unset would leave the rows
    of a headroom comparison measuring the same thing twice.
    """
    modules = [policy, import_module(objective_scale.__module__), core]
    reading = [module for module in modules if hasattr(module, "HEADROOM")]
    originals = [module.HEADROOM for module in reading]

    with set_headroom(1.0):
        for module in reading:
            assert pytest.approx(1.0) == module.HEADROOM, module.__name__

    for module, original in zip(reading, originals, strict=True):
        assert pytest.approx(original) == module.HEADROOM, module.__name__


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
            # The rungs are the probes, and the ladder the stub builds has to be
            # the ladder a sweeping master is asked for, so both are sent.
            assert settings == {
                "convexity_sweep_max": 100.0,
                "convexity_sweep_points": ADAPTIVE["number_of_parallel_points"],
            }
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
