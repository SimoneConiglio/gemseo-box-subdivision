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
"""The estimator of the basin spacing, against landscapes whose count is known.

The benchmark itself is too expensive for the tests, so what is checked here is
the estimator: that it counts the basins of a landscape whose basins can be
counted by hand, that its amplitude gate leaves a flat component alone, and that
it reports a landscape it has not resolved as unresolved rather than settling on
the count it happens to have reached.
"""

from __future__ import annotations

import logging

import pytest
from numpy import array
from numpy import cos
from numpy import linspace
from numpy import pi
from numpy import sum as np_sum

from benchmarks.basin_spacing import DEFAULT_STALL
from benchmarks.basin_spacing import DIMENSION
from benchmarks.basin_spacing import count_minima
from benchmarks.basin_spacing import estimate_basins
from benchmarks.basin_spacing import group_by_density
from benchmarks.basin_spacing import run_at_density
from benchmarks.basin_spacing import run_at_density_swept
from benchmarks.basin_spacing import stall_counter
from benchmarks.problems import PROBLEMS


def test_count_minima_prominence():
    """A dip is worth its key saddle, not the highest ground anywhere beside it.

    Ripples a hundredth of the range deep, riding a bowl a hundred times their
    depth, are not basins the subdivision has to separate. Measuring a dip
    against the highest point anywhere on each side makes every one of them look
    as deep as the bowl, which is what this counted until it was checked.
    """
    abscissae = linspace(0.0, 1.0, 401)
    deep = cos(2.0 * pi * 3.0 * abscissae)
    assert count_minima(deep) == 3

    # The same three dips under a slope that dwarfs them.
    assert count_minima(1000.0 * abscissae + deep, depth_ratio=0.02) == 1

    # Twenty ripples 1% of the range deep, in phase with the bowl they ride.
    bowl = linspace(-10.0, 10.0, 4001)
    assert count_minima(bowl**2 - 0.5 * cos(2.0 * pi * bowl), 0.02) == 1

    # Out of phase, the bowl's own minimum is genuinely split in two by a ridge
    # standing above both, and two is then the honest answer.
    assert count_minima(bowl**2 + 0.5 * cos(2.0 * pi * bowl), 0.02) == 2


def test_count_minima_constant():
    """A component the objective does not vary in holds a single basin."""
    assert count_minima(linspace(1.0, 1.0, 50)) == 1


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Minima about one unit apart over a range of ten.
        ("rastrigin", 10),
        # A quartic double well, whatever the other components do.
        ("styblinski_tang", 2),
    ],
)
def test_estimate_counts_the_basins(name, expected):
    """The scans recover a basin count that can be worked out by hand."""
    problem = PROBLEMS[name]
    estimate = estimate_basins(
        lambda points: array([problem.objective(point) for point in points]),
        problem.lower_bound,
        problem.upper_bound,
    )
    assert estimate.converged
    assert all(abs(count - expected) <= 1 for count in estimate.n_subdivisions), (
        estimate.n_subdivisions
    )


def test_estimate_selects_the_multimodal_variables():
    """The amplitude gate leaves the components carrying no basin alone.

    ``partly_multimodal`` is Rastrigin on its first two components and a
    paraboloid on the other three, so an estimate that proposes a density per
    variable has to propose a single subdivision for the paraboloid ones. That
    is the partial refinement of ``refine_some_variables.py``, reached from the
    landscape instead of being declared.
    """
    problem = PROBLEMS["partly_multimodal"]
    estimate = estimate_basins(
        lambda points: array([problem.objective(point) for point in points]),
        problem.lower_bound,
        problem.upper_bound,
    )
    assert estimate.converged
    assert all(count >= 9 for count in estimate.n_subdivisions[:2])
    assert estimate.n_subdivisions[2:] == (1, 1, 1)


def test_estimate_reports_what_it_has_not_resolved():
    """Ackley is not resolved by this ladder, and the estimate says so.

    The error of the estimator is one sided: a scan reveals the basins it
    resolves and never more. Ackley's ripples are one unit apart over a range of
    sixty, so the ladder is still climbing when it runs out of rungs, and what
    matters is that the estimate is marked unresolved rather than returning the
    count it stopped at as though it had settled there.
    """
    problem = PROBLEMS["ackley"]
    estimate = estimate_basins(
        lambda points: array([problem.objective(point) for point in points]),
        problem.lower_bound,
        problem.upper_bound,
    )
    assert not estimate.converged
    assert all(count > 40 for count in estimate.n_subdivisions), estimate.n_subdivisions


def test_uniform_scan_aliases_silently():
    """An evenly spaced scan settles on the wrong count, which is why it is not used.

    Ackley's ripples are one unit apart and its range is about sixty-four, so an
    even scan whose spacing approaches one resonates with them and reports a
    single basin. It does so at two consecutive rungs, which any stopping rule
    reads as convergence, and this is the failure the jitter exists to prevent.
    """
    problem = PROBLEMS["ackley"]
    uniform = estimate_basins(
        lambda points: array([problem.objective(point) for point in points]),
        problem.lower_bound,
        problem.upper_bound,
        jitter=False,
    )
    assert uniform.converged
    assert max(uniform.n_subdivisions) <= 2, uniform.n_subdivisions


def test_group_by_density():
    """Components sharing a density share a variable, and the flat ones are free."""
    assert group_by_density((10, 10, 1, 1, 1)) == {
        "x_m10": (0, 1),
        "x_free": (2, 3, 4),
    }
    assert group_by_density((19, 9, 11, 9, 8)) == {
        "x_m19": (0,),
        "x_m9": (1, 3),
        "x_m11": (2,),
        "x_m8": (4,),
    }


def test_stall_counter_follows_the_binaries():
    """Patience follows the density, and never drops below the catalogue default.

    Ten stalling iterations is a count of mistakes tolerated rather than a
    property of a problem. A finer subdivision proposes more boxes, and a trust
    region held open at ``MIN_STEP`` keeps proposing from a neighbourhood it has
    not exhausted, so both make a run stall more often for the same progress.
    Holding the region open while leaving the patience at ten costs Rastrigin
    its result, and sizing the two together keeps it.
    """
    assert stall_counter((2, 2, 2, 2, 2)) == DEFAULT_STALL
    assert stall_counter((10, 10, 10, 10, 10)) == 50
    assert stall_counter((10, 10, 1, 1, 1)) == 23


def test_run_at_density_refines_per_variable():
    """A density per variable solves the problem a partial refinement is for."""
    logging.disable(logging.CRITICAL)
    problem = PROBLEMS["partly_multimodal"]
    best, cost, truncated = run_at_density(
        problem, DIMENSION, (10, 10, 1, 1, 1), seed=11, budget=2500
    )
    assert not truncated
    assert best - problem.optimum(DIMENSION) == pytest.approx(0.0, abs=1e-3)
    assert cost < 2500


def test_swept_solves_what_the_calibrated_margin_loses():
    """With no convexity supplied, Ackley is solved where the margin loses it.

    ``min_dfk`` is absolute, in the units of the objective, and the calibrated
    hundred is 690% of the range Ackley spans, so the repair is driven by the
    margin rather than by the measurements and the cuts rank nothing: the same
    density returns a gap of $6.30$ and reaches the optimum from one starting
    point out of three. Sweeping supplies no margin and reaches it from two,
    which is what is asserted here rather than a seed that happens to work.
    """
    logging.disable(logging.CRITICAL)
    problem = PROBLEMS["ackley"]
    optimum = problem.optimum(DIMENSION)
    gaps = [
        run_at_density_swept(
            problem, DIMENSION, (10,) * DIMENSION, seed=seed, budget=8000
        )[0]
        - optimum
        for seed in (11, 101, 202)
    ]
    assert sum(gap < 1e-2 for gap in gaps) >= 2, gaps


def test_objective_is_the_problem():
    """The grouped discipline reassembles the components in their own order."""
    problem = PROBLEMS["partly_multimodal"]
    point = linspace(-1.0, 1.0, DIMENSION)
    head, tail = point[:2], point[2:]
    expected = float(
        np_sum(10.0 + head**2 - 10.0 * cos(2.0 * pi * head)) + np_sum(tail**2)
    )
    assert problem.objective(point) == pytest.approx(expected)
