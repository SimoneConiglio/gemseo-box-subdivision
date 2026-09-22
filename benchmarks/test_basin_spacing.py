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
from benchmarks.basin_spacing import stall_counter
from benchmarks.problems import PROBLEMS


def test_count_minima_prominence():
    """A dip shallower than the gate is texture, a deeper one is a basin."""
    abscissae = linspace(0.0, 1.0, 401)
    deep = cos(2.0 * pi * 3.0 * abscissae)
    assert count_minima(deep) == 3

    # The same three dips, now a thousandth of the range of a dominating slope.
    shallow = 1000.0 * abscissae + deep
    assert count_minima(shallow, depth_ratio=0.02) == 1


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

    The master gives up after so many iterations that improve nothing, and ten
    of them is a count of mistakes tolerated rather than a property of the
    problem. A subdivision proposing more boxes has to make more mistakes to
    cover them, so a density that incites exploration and leaves the patience
    where it was stops the run for doing what it was asked to do.
    """
    assert stall_counter((2, 2, 2, 2, 2)) == DEFAULT_STALL
    assert stall_counter((10, 10, 10, 10, 10)) == 50
    assert stall_counter((63, 63, 62, 63, 63)) == 314


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


def test_objective_is_the_problem():
    """The grouped discipline reassembles the components in their own order."""
    problem = PROBLEMS["partly_multimodal"]
    point = linspace(-1.0, 1.0, DIMENSION)
    head, tail = point[:2], point[2:]
    expected = float(
        np_sum(10.0 + head**2 - 10.0 * cos(2.0 * pi * head)) + np_sum(tail**2)
    )
    assert problem.objective(point) == pytest.approx(expected)
