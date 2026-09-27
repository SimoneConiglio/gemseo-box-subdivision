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
from numpy import atleast_2d
from numpy import cos
from numpy import linspace
from numpy import pi
from numpy import sum as np_sum

from benchmarks.basin_spacing import DEFAULT_STALL
from benchmarks.basin_spacing import DIMENSION
from benchmarks.basin_spacing import NoFeasibleScanError
from benchmarks.basin_spacing import count_minima
from benchmarks.basin_spacing import count_minima_over_feasible
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
    outcome = run_at_density(
        problem, DIMENSION, (10, 10, 1, 1, 1), seed=11, budget=2500
    )
    assert not outcome.truncated
    assert outcome.best - problem.optimum(DIMENSION) == pytest.approx(0.0, abs=1e-3)
    assert outcome.cost < 2500
    # The database counted the same run, in its own unit and over its boxes.
    assert 0 < outcome.evaluations < outcome.cost
    assert outcome.boxes > 0


def test_the_database_counts_what_a_fork_takes_away():
    """The measures read from the master's database survive the fan-out.

    The master solves its candidate boxes over forked workers, so a counter kept
    in the parent stops counting where the fan-out begins: here it reports a
    best value of $0.0000$ at one process and $33.4089$ at four, for a run that
    reached the optimum both times. That is what moved the counting to the
    database, and what is asserted is the property the move was made for --
    identical numbers at one process and at four, not merely plausible ones.

    The cost is deliberately left out of the comparison. It is the counter's,
    in the unit `baselines.py` reports, and the database cannot return it: the
    adapter of the sub-scenario exports the length of the sub-problem's
    database, a count of points, where the cost counts an objective call plus a
    gradient call.
    """
    logging.disable(logging.CRITICAL)
    problem = PROBLEMS["partly_multimodal"]
    density = (10, 10, 1, 1, 1)
    serial = run_at_density(problem, DIMENSION, density, seed=11, budget=2500)
    parallel = run_at_density(
        problem, DIMENSION, density, seed=11, budget=2500, n_processes=4
    )
    assert parallel.best == serial.best
    assert parallel.evaluations == serial.evaluations
    assert parallel.boxes == serial.boxes


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
        ).best
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


LOWER, UPPER = -5.0, 5.0


def _mass(points):
    """A mass-like objective: linear, so monotone along every line."""
    return atleast_2d(points).sum(axis=1)


def _disconnected(points):
    r"""A stress-like limit whose feasible set falls into pieces on each axis.

    Feasible where $\\cos(\\pi x) \\le 1/2$ in every component, which over a range
    of ten is six intervals per axis.
    """
    return (cos(pi * atleast_2d(points)) - 0.5).max(axis=1)


def test_the_objective_alone_cannot_see_a_constraint_driven_landscape():
    """The failure this is for, pinned so it is not mistaken for a result.

    A mass is monotone along every line, so its scan finds one basin and is
    right about the objective. The constrained problem has six per axis. The
    estimate is not merely wrong, it is **confident**: the ladder converges,
    because there is nothing in the objective for a finer scan to find.
    """
    estimate = estimate_basins(_mass, LOWER, UPPER, dimension=3, seed=0)
    assert estimate.n_subdivisions == (1, 1, 1)
    assert estimate.converged


def test_the_feasible_pieces_are_counted_when_the_constraint_is_given():
    """Given the constraint, the same landscape reports the density it needs."""
    estimate = estimate_basins(
        _mass, LOWER, UPPER, dimension=3, seed=0, constraint=_disconnected
    )
    assert estimate.n_subdivisions == (6, 6, 6)


def test_an_empty_feasible_set_raises_rather_than_answering():
    """No feasible scan is not the same as one basin, and must not read as one.

    A line drawn through an infeasible anchor carries no information. Were such
    a line counted, it would count as a single basin and the estimate would come
    back exactly as it does with no constraint at all -- the confident wrong
    answer this is meant to remove.
    """
    with pytest.raises(NoFeasibleScanError, match="feasible point"):
        estimate_basins(
            _mass,
            LOWER,
            UPPER,
            dimension=3,
            seed=0,
            constraint=lambda points: atleast_2d(points)[:, 0] * 0.0 + 1.0,
        )


def test_a_boundary_minimum_is_a_basin():
    """An interval whose objective is monotone still holds one basin.

    Its minimum sits where the interval ends, which is where the active set
    changes, and the subdivision has to separate it exactly as it would an
    interior one. Three feasible pieces under a monotone objective are three.
    """
    values = linspace(0.0, 10.0, 300)
    feasible = array([False] * 300)
    feasible[10:50] = True
    feasible[100:140] = True
    feasible[200:240] = True
    assert count_minima_over_feasible(values, feasible) == 3


def test_interior_minima_are_counted_within_a_piece():
    """A single feasible piece holding three dips is worth three, not one.

    401 points rather than a round 900: an even grid can straddle a minimum so
    that no descent is followed by an ascent, and this same cosine counts two at
    900 points and three at 401 or 901. That is the aliasing the estimator draws
    its abscissae at random to avoid, showing up here in miniature.
    """
    abscissae = linspace(0.0, 1.0, 401)
    values = cos(2.0 * pi * 3.0 * abscissae)
    feasible = array([True] * 401)
    assert count_minima_over_feasible(values, feasible) == 3


def test_a_narrow_feasible_sliver_does_not_promote_its_ripples():
    """The prominence gate is read against the line, not against the piece.

    Ripples a thousandth of the line's range deep are not basins the
    subdivision has to separate. Measured against the range of the sliver they
    live in they would look like the whole landscape, which is why the range of
    the scan is passed down rather than recomputed per piece.
    """
    abscissae = linspace(-10.0, 10.0, 4001)
    # The tilt is not decoration. Without it the two lowest ripples tie exactly,
    # and `count_minima` holds a minimum open on every side to be worth the whole
    # range, so both survive any gate. That is a property of the prominence rule
    # rather than of the narrowness this test is about.
    values = abscissae**2 + 0.05 * cos(40.0 * pi * abscissae) + 0.002 * abscissae
    feasible = abs(abscissae) < 0.25  # a sliver at the bottom of the bowl
    assert count_minima_over_feasible(values, feasible) == 1
    # Against the sliver's own range those same ten ripples are all basins.
    assert count_minima(values[feasible]) == 10
