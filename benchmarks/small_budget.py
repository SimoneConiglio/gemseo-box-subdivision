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
"""The five methods at a budget every one of them can afford.

The benchmark's budgets, 500 equivalent evaluations per variable, are far outside
the regime Bayesian optimization is built for: SEGO refits a Gaussian process at
every iteration, at a cost cubic in the number of points. One run of five
hundred evaluations
takes some two and a half minutes against three seconds for the box
subdivision, and the budgets of the main comparison are two to five times
larger again, so comparing it there would measure wall time rather than method
quality.

This is the comparison at a budget every method can afford, which is also the
regime closest to the case the method targets: an objective costing minutes,
where a few hundred evaluations is the whole budget.
"""

from __future__ import annotations

import logging
import time
from statistics import median

from benchmarks.baselines import METHODS
from benchmarks.baselines import run
from benchmarks.problems import PROBLEMS

logging.disable(logging.CRITICAL)

BUDGET = 500
SEEDS = (11, 101, 202)
PROBLEM_NAMES = ("rastrigin", "ackley", "styblinski_tang", "griewank")

print(
    f"Budget {BUDGET} equivalent evaluations, median over {len(SEEDS)} "
    f"starting points\n",
    flush=True,
)
print(
    f"{'problem':>17} {'n':>2} {'method':>16} {'gap':>9} {'cost':>6}"
    f" {'reached':>8} {'seconds':>8}",
    flush=True,
)
for dimension in (2, 5):
    for name in PROBLEM_NAMES:
        problem = PROBLEMS[name]
        optimum = problem.optimum(dimension)
        for method in METHODS:
            start = time.time()
            gaps = []
            costs = []
            for seed in SEEDS:
                outcome = run(method, problem, dimension, seed, BUDGET)
                gaps.append(outcome.gap(optimum))
                costs.append(outcome.cost_adjoint)

            print(
                f"{name:>17} {dimension:>2} {method:>16} {median(gaps):>9.3f}"
                f" {median(costs):>6.0f}"
                f" {sum(g <= 1e-4 for g in gaps)}/{len(gaps)}"
                f" {time.time() - start:>8.1f}",
                flush=True,
            )
