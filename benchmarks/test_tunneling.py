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
"""Check the tunneling baseline: its function, its poles and its budget."""

from __future__ import annotations

import logging
from itertools import pairwise

import pytest
from numpy import array
from numpy import eye
from numpy import isfinite
from numpy import zeros
from numpy.linalg import norm

from benchmarks.baselines import run
from benchmarks.problems import PROBLEMS
from benchmarks.problems import Counter
from benchmarks.problems import Problem
from benchmarks.problems import rastrigin
from benchmarks.problems import rastrigin_gradient
from benchmarks.tunneling import SETTINGS
from benchmarks.tunneling import _solve
from benchmarks.tunneling import tunnel
from benchmarks.tunneling import tunneling_function


def _sphere(x):
    return float(x @ x)


def _sphere_gradient(x):
    return 2.0 * x


SPHERE = Problem("sphere", _sphere, _sphere_gradient, -1.3, 1.7, lambda n: 0.0)  # noqa: ARG005
"""A problem with a single minimum, where every tunneling search must fail."""


@pytest.mark.parametrize("strength", [1.0, 1.3])
def test_gradient_of_the_tunneling_function(strength) -> None:
    """Check the analytic gradient against centred finite differences."""
    x_star = array([0.98, -0.02])
    f_star = rastrigin(x_star)
    poles = [(array([1.6, 0.4]), 1.0), (array([0.2, -0.7]), 1.0)]
    x = array([1.31, -0.47])

    def value(point):
        return tunneling_function(
            rastrigin(point),
            rastrigin_gradient(point),
            point,
            x_star,
            f_star,
            strength,
            poles,
        )

    gradient = value(x)[1]
    step = 1e-6
    for i, direction in enumerate(eye(2)):
        difference = (
            value(x + step * direction)[0] - value(x - step * direction)[0]
        ) / (2 * step)
        assert gradient[i] == pytest.approx(difference, rel=1e-5, abs=1e-6)


def test_the_value_of_the_tunneling_function() -> None:
    """Check the tunneling function against its definition."""
    x = array([1.0, 2.0])
    value, _ = tunneling_function(
        7.0, zeros(2), x, zeros(2), 2.0, 1.5, [(array([1.0, 0.0]), 1.0)]
    )
    assert value == pytest.approx((7.0 - 2.0) / (5.0**1.5 * 4.0))


def test_the_pole_keeps_the_search_away_from_the_minimizer() -> None:
    """Check that minimizing the tunneling function leaves the minimizer.

    On a sphere, the numerator vanishes quadratically at the minimizer, so
    without the pole the minimizer is the zero the search would return to. With
    a pole slightly stronger than that zero, the function decreases away from it
    and the search ends on the bounds, far from it.
    """
    x_star = zeros(2)
    start = array([0.01, 0.02])

    def function(x):
        return tunneling_function(_sphere(x), zeros(2), x, x_star, 0.0, 1.1)[0]

    def jacobian(x):
        return tunneling_function(_sphere(x), _sphere_gradient(x), x, x_star, 0.0, 1.1)[
            1
        ]

    logging.disable(logging.CRITICAL)
    x_m, value = _solve(-1.3, 1.7, start, function, jacobian, SETTINGS.max_iter)
    logging.disable(logging.NOTSET)
    assert norm(x_m - x_star) > 50 * norm(start - x_star)
    assert value > 0.0


def test_a_single_minimum_stops_the_method_on_its_own() -> None:
    """Check that every tunneling search fails on a sphere, ending the run."""
    counter = Counter(SPHERE)
    logging.disable(logging.CRITICAL)
    minima = tunnel(
        counter, 2, SPHERE.lower_bound, SPHERE.upper_bound, array([1.0, -1.0]), 11
    )
    logging.disable(logging.NOTSET)
    assert len(minima) == 1
    assert norm(minima[0][0]) < 1e-4
    assert counter.n_objective > 0
    assert counter.n_gradient > 0


def test_tunneling_descends() -> None:
    """Check the generalized descent property on Rastrigin."""
    counter = Counter(PROBLEMS["rastrigin"])
    logging.disable(logging.CRITICAL)
    minima = tunnel(counter, 2, -4.1, 5.9, array([3.2, -2.9]), 11)
    logging.disable(logging.NOTSET)
    values = [value for _, value in minima]
    assert len(values) > 1
    assert all(b < a for a, b in pairwise(values))


@pytest.mark.parametrize("name", ["rastrigin", "ackley", "styblinski_tang", "griewank"])
@pytest.mark.parametrize("dimension", [2, 5])
def test_budget_and_outcome(name, dimension) -> None:
    """Check that a run respects its budget and evaluates something finite.

    The budget is the counter's, which every call of the tunneling function goes
    through, so it is exact; the history has one entry per evaluation charged.
    """
    budget = 300
    result = run("tunneling", PROBLEMS[name], dimension, 101, budget)
    assert result.n_objective > 0
    assert isfinite(result.best)
    assert result.cost_adjoint <= budget
    assert len(result.history) == result.cost_adjoint
    assert result.history[-1] == result.best
