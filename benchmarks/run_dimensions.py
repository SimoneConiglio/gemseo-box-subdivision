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
"""Run the method, its ablations and the baselines in 10 and 20 variables.

The budget is that of five variables, $2500$ equivalent evaluations, whatever
the dimension, so that the evaluations per variable decrease as the dimension
increases. The methods are run on the four problems from the twenty starting
points of :mod:`benchmarks.run_statistics`:

- the swept configuration with the default density, two subdivisions per
  variable (``swept``), and with ten (``density_10``);
- its ablations at the default density, a random box within the trust region
  (``random_box``) and slopes set to zero (``zero_slopes``);
- the multistart algorithm, CMA-ES and IPOP-CMA-ES, DIRECT with and without its
  local bias, MLSL and the classic tunneling method.

EGO, limited to $500$ evaluations by the cost of its surrogate model, is not run.
The targets of the data profiles of each dimension are generated from the runs
of all these methods. The method is compared with each other one by the tests of
:mod:`benchmarks.statistics`, the Holm correction running over the four problems
and the other methods. Five variables are summarized from the runs of
:mod:`benchmarks.run_statistics` and :mod:`benchmarks.run_review`, which have the
same budget, against the published targets; there, the ablations were run with
ten subdivisions per variable. The summary is written to
``docs/_static/dimensions.json``.

```shell
OMP_NUM_THREADS=1 python -m benchmarks.run_dimensions
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
from benchmarks.run_statistics import SEEDS
from benchmarks.statistics import change_points
from benchmarks.statistics import compare
from benchmarks.statistics import compare_areas
from benchmarks.statistics import run_area

DIMENSIONS = (10, 20)
"""The numbers of design variables run here."""

BUDGET = 2500
"""The budget of every method and dimension, that of five variables."""

METHODS = (
    "swept",
    "density_10",
    "random_box",
    "zero_slopes",
    "multistart",
    "cmaes",
    "ipop_cmaes",
    "direct",
    "direct_global",
    "mlsl",
    "tunneling",
)
"""The methods, the reference first."""

REFERENCE = "swept"
"""The method the others are compared with in 10 and 20 variables."""

OUTPUT = data_profiles.OUTPUT.with_name("dimensions.json")
"""The file of the summaries."""


def _table(runs: list[dict], targets: dict, dimension: int) -> dict:
    """Return the outcome of every run, keyed by method, problem and seed."""
    table = {}
    for run in runs:
        problem = run["problem"]
        optimum = PROBLEMS[problem].optimum(dimension)
        gap = run["best"] - optimum
        table[run["method"], problem, run["seed"]] = {
            "gap": gap,
            "cost": run["cost_adjoint"],
            "reached": gap <= data_profiles.TOLERANCE * max(1.0, abs(optimum)),
            "area": run_area(run["history"], targets[problem], BUDGET),
            "history": change_points(run["history"]),
        }
    return table


def _summary(table: dict, methods: tuple[str, ...]) -> dict:
    """Return the success, the median distance and cost, and the mean area."""
    return {
        method: {
            "area": sum(
                table[method, p, s]["area"]
                for p in data_profiles.PROBLEM_NAMES
                for s in SEEDS
            )
            / (len(data_profiles.PROBLEM_NAMES) * len(SEEDS)),
            **{
                problem: {
                    "reached": sum(table[method, problem, s]["reached"] for s in SEEDS),
                    "median_gap": median(
                        table[method, problem, s]["gap"] for s in SEEDS
                    ),
                    "median_cost": median(
                        table[method, problem, s]["cost"] for s in SEEDS
                    ),
                }
                for problem in data_profiles.PROBLEM_NAMES
            },
        }
        for method in methods
        if all(
            (method, p, s) in table for p in data_profiles.PROBLEM_NAMES for s in SEEDS
        )
    }


def _five_variables() -> dict:
    """Return the summary of five variables, from the runs already made."""
    published = json.loads(data_profiles.OUTPUT.read_text(encoding="utf-8"))
    targets = published["dimensions"]["5"]["targets"]
    runs = [
        json.loads(line)
        for name in ("5.jsonl", "review-5.jsonl")
        for line in (CACHE / name).read_text().splitlines()
    ]
    runs = [run for run in runs if run["method"] in METHODS]
    summary = _summary(_table(runs, targets, 5), METHODS)
    return {"budget": BUDGET, "summary": summary}


def main() -> None:
    """Run every method in 10 and 20 variables and write the summaries."""
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    output = {"5": _five_variables()}
    for dimension in DIMENSIONS:
        results = data_profiles.collect(
            dimension,
            METHODS,
            seeds=SEEDS,
            cache=CACHE / f"dimensions-{dimension}.jsonl",
            budget=BUDGET,
        )
        print(f"{dimension} variables: {len(results)} runs", flush=True)  # noqa: T201
        targets = data_profiles.compute_targets(results)
        runs = [
            json.loads(line)
            for line in (CACHE / f"dimensions-{dimension}.jsonl")
            .read_text()
            .splitlines()
        ]
        table = _table(runs, targets, dimension)
        problems = data_profiles.PROBLEM_NAMES
        others = tuple(m for m in METHODS if m != REFERENCE)
        tests = compare(table, REFERENCE, others, problems)
        areas = compare_areas(table, REFERENCE, others, problems)
        output[str(dimension)] = {
            "budget": BUDGET,
            "summary": _summary(table, METHODS),
            "tests": tests,
            "areas": areas,
        }
        for name, entry in output[str(dimension)]["summary"].items():
            print(  # noqa: T201
                f"{dimension:>3} {name:>14} area {entry['area']:.2f} "
                + " ".join(
                    f"{p[:4]} {entry[p]['reached']:>2} {entry[p]['median_gap']:.3g}"
                    for p in problems
                ),
                flush=True,
            )
    OUTPUT.write_text(json.dumps(output, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
