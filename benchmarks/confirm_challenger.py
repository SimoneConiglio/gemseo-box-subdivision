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
r"""Confirm a challenger of the configuration on new starting points.

A challenger found clearly better by :mod:`benchmarks.statistics` was selected
among several on the twenty starting points of the comparison, so that its
advantage is overestimated. It is run again with the configuration from twenty
other starting points, :data:`SEEDS`, and the difference of area is given with
its paired bootstrap interval, together with the McNemar test of the success on
each problem, Holm-corrected over the problems.

```shell
python -m benchmarks.confirm_challenger 2 probes_16
```
"""

from __future__ import annotations

import json
import logging
import sys
import warnings

from numpy import array
from numpy import mean
from numpy import percentile
from numpy.random import default_rng

from benchmarks import data_profiles
from benchmarks.problems import PROBLEMS
from benchmarks.run_statistics import CACHE
from benchmarks.run_statistics import COMPARED
from benchmarks.statistics import N_BOOTSTRAP
from benchmarks.statistics import holm
from benchmarks.statistics import mcnemar
from benchmarks.statistics import run_area

SEEDS = tuple(range(2021, 4000, 101))[:20]
"""The twenty seeds of the new starting points, none of the comparison."""


def main(dimension: int, challenger: str) -> dict:
    """Run and compare the configuration and a challenger on new starting points.

    Args:
        dimension: The number of design variables.
        challenger: The name of the challenger.

    Returns:
        The success of each method on each problem, the tests and the areas.
    """
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    method = COMPARED[dimension]
    results = data_profiles.collect(
        dimension,
        (method, challenger),
        seeds=SEEDS,
        cache=CACHE / f"{dimension}-confirmation.jsonl",
    )
    published = json.loads(data_profiles.OUTPUT.read_text(encoding="utf-8"))
    targets = published["dimensions"][str(dimension)]["targets"]
    budget = data_profiles.budget_of(method, dimension)
    reached = {}
    area = {}
    for result in results:
        optimum = PROBLEMS[result.problem].optimum(dimension)
        key = (result.method, result.problem, result.seed)
        reached[key] = result.best - optimum <= data_profiles.TOLERANCE * max(
            1.0, abs(optimum)
        )
        area[key] = run_area(result.history, targets[result.problem], budget)

    problems = data_profiles.PROBLEM_NAMES
    tests = []
    for problem in problems:
        only_method, only_challenger, p_value = mcnemar(
            [reached[method, problem, s] for s in SEEDS],
            [reached[challenger, problem, s] for s in SEEDS],
        )
        tests.append({
            "problem": problem,
            "reached": [
                sum(reached[name, problem, s] for s in SEEDS)
                for name in (method, challenger)
            ],
            "only_method": only_method,
            "only_challenger": only_challenger,
            "p_success": p_value,
        })
    for test, corrected in zip(
        tests, holm([t["p_success"] for t in tests]), strict=True
    ):
        test["p_success_holm"] = corrected

    per_seed = {
        name: array([mean([area[name, p, s] for p in problems]) for s in SEEDS])
        for name in (method, challenger)
    }
    difference = per_seed[challenger] - per_seed[method]
    samples = default_rng(0).integers(0, len(SEEDS), size=(N_BOOTSTRAP, len(SEEDS)))
    boot = difference[samples].mean(axis=1)
    return {
        "method": method,
        "challenger": challenger,
        "seeds": list(SEEDS),
        "tests": tests,
        "area_method": float(per_seed[method].mean()),
        "area_challenger": float(per_seed[challenger].mean()),
        "difference": float(difference.mean()),
        "ci95": [float(percentile(boot, 2.5)), float(percentile(boot, 97.5))],
    }


if __name__ == "__main__":
    print(json.dumps(main(int(sys.argv[1]), sys.argv[2]), indent=1))  # noqa: T201
