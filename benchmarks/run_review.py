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
"""Run the ablations of the master problem.

Three ablations of the configuration compared with the baselines:

- ``random_box``: the master problem replaced by a random choice among the
  boxes not yet solved within the trust region of each probe;
- ``zero_slopes``: the slopes of the cuts set to zero before the repair, so that
  the cuts carry only the values observed;
- ``random_slopes``: each slope replaced by a random vector of the same norm.

The baselines spending their budget, first run here, belong to the main
comparison of :mod:`benchmarks.run_statistics`.

Each is run from the twenty starting points of :mod:`benchmarks.run_statistics`
and compared with the configuration by the tests of :mod:`benchmarks.statistics`,
the Holm correction running over the four problems and these methods. The
runs are kept in ``benchmarks/.statistics/review-{n}.jsonl``, the summaries in
``docs/_static/review.json``.

```shell
OMP_NUM_THREADS=1 python -m benchmarks.run_review
```
"""

from __future__ import annotations

import json
import logging
import warnings
from statistics import median

from benchmarks import data_profiles
from benchmarks.problems import PROBLEMS
from benchmarks.run_statistics import CACHE
from benchmarks.run_statistics import COMPARED
from benchmarks.run_statistics import SEEDS
from benchmarks.statistics import change_points
from benchmarks.statistics import compare
from benchmarks.statistics import compare_areas
from benchmarks.statistics import run_area

METHODS = ("random_box", "zero_slopes", "random_slopes")
"""The ablations and the baselines spending their budget."""

OUTPUT = data_profiles.OUTPUT.with_name("review.json")
"""The file of the summaries."""


def _table(runs: list[dict], targets: dict, dimension: int) -> dict:
    """Return the outcome of every run, keyed by method, problem and seed.

    Args:
        runs: The runs.
        targets: The published targets of each problem.
        dimension: The number of design variables.

    Returns:
        The distance, the cost, the success, the area and the history.
    """
    table = {}
    for run in runs:
        problem = run["problem"]
        optimum = PROBLEMS[problem].optimum(dimension)
        budget = data_profiles.budget_of(run["method"], dimension)
        gap = run["best"] - optimum
        table[run["method"], problem, run["seed"]] = {
            "gap": gap,
            "cost": run["cost_adjoint"],
            "reached": gap <= data_profiles.TOLERANCE * max(1.0, abs(optimum)),
            "area": run_area(run["history"], targets[problem], budget),
            "history": change_points(run["history"]),
        }
    return table


def main() -> None:
    """Run the methods, compare them with the configuration and write a summary."""
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    published = json.loads(data_profiles.OUTPUT.read_text(encoding="utf-8"))
    output = {}
    for dimension in data_profiles.DIMENSIONS:
        results = data_profiles.collect(
            dimension, METHODS, seeds=SEEDS, cache=CACHE / f"review-{dimension}.jsonl"
        )
        print(f"{dimension} variables: {len(results)} runs", flush=True)  # noqa: T201
        runs = [
            json.loads(line)
            for name in (f"{dimension}.jsonl", f"review-{dimension}.jsonl")
            for line in (CACHE / name).read_text().splitlines()
        ]
        method = COMPARED[dimension]
        runs = [r for r in runs if r["method"] in {method, *METHODS}]
        targets = published["dimensions"][str(dimension)]["targets"]
        table = _table(runs, targets, dimension)
        problems = data_profiles.PROBLEM_NAMES
        tests = compare(table, method, METHODS, problems)
        areas = compare_areas(table, method, METHODS, problems)
        summary = {
            name: {
                problem: {
                    "reached": sum(
                        table[name, problem, seed]["reached"] for seed in SEEDS
                    ),
                    "median_gap": median(
                        table[name, problem, seed]["gap"] for seed in SEEDS
                    ),
                    "median_cost": median(
                        table[name, problem, seed]["cost"] for seed in SEEDS
                    ),
                }
                for problem in problems
            }
            for name in (method, *METHODS)
        }
        output[str(dimension)] = {
            "method": method,
            "summary": summary,
            "tests": tests,
            "areas": areas,
        }
        for test in tests:
            print(  # noqa: T201
                f"{test['baseline']:>14} {test['problem']:>15}"
                f" {test['reached'][0]:>3}/{test['reached'][1]:<3}"
                f" Holm success {test['p_success_holm']:.3f}"
                f" Holm gap {test['p_gap_holm']:.3f}"
            )
        for area in areas:
            print(  # noqa: T201
                f"area {area['baseline']:>14}: {area['area_method']:.3f} vs"
                f" {area['area_baseline']:.3f}, difference {area['difference']:+.3f}"
                f" [{area['ci95'][0]:+.3f}, {area['ci95'][1]:+.3f}]"
            )
        for name in (method, *METHODS):
            costs = {p: summary[name][p]["median_cost"] for p in problems}
            print(f"cost {name:>14}: {costs}")  # noqa: T201

    OUTPUT.write_text(json.dumps(output, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
