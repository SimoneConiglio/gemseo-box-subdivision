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
r"""The comparison at a budget of 500 evaluations, from twenty starting points.

Every method, the box subdivision in the configuration compared with the
baselines and the five baselines, is given $500$ equivalent evaluations in two
and five variables, from the twenty starting points of
:mod:`benchmarks.run_statistics`. The runs are kept in
``benchmarks/.statistics/small-{n}.jsonl``; those of EGO, whose budget is
already $500$ in the main comparison, are taken from its cache when present.

The method is compared with each baseline by the tests of
:mod:`benchmarks.statistics` on the final distance, the Holm correction running
over the problems and the baselines of each dimension. The results are written
to ``docs/_static/small_budget.json``.

```shell
OMP_NUM_THREADS=1 python -m benchmarks.small_budget_statistics
```
"""

from __future__ import annotations

import json
import logging
import warnings
from statistics import median

from benchmarks import data_profiles
from benchmarks.problems import PROBLEMS
from benchmarks.run_statistics import BASELINES
from benchmarks.run_statistics import CACHE
from benchmarks.run_statistics import COMPARED
from benchmarks.run_statistics import SEEDS
from benchmarks.statistics import compare

BUDGET = 500
"""The budget of every method, in equivalent evaluations."""

OUTPUT = data_profiles.OUTPUT.with_name("small_budget.json")
"""The file the results are written to."""


def _seed_from_the_main_cache(dimension: int) -> None:
    """Copy the runs of EGO of the main comparison, whose budget is the same.

    Args:
        dimension: The number of design variables.
    """
    source = CACHE / f"{dimension}.jsonl"
    target = CACHE / f"small-{dimension}.jsonl"
    if target.exists() or not source.exists():
        return
    lines = [
        line
        for line in source.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["method"] == "egobox"
    ]
    target.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def main() -> None:
    """Run every method at the small budget, then compare and write the results."""
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    output = {"budget": BUDGET, "seeds": list(SEEDS), "dimensions": {}}
    for dimension in data_profiles.DIMENSIONS:
        _seed_from_the_main_cache(dimension)
        method = COMPARED[dimension]
        results = data_profiles.collect(
            dimension,
            (method, *BASELINES),
            seeds=SEEDS,
            cache=CACHE / f"small-{dimension}.jsonl",
            budget=BUDGET,
        )
        table = {}
        for result in results:
            optimum = PROBLEMS[result.problem].optimum(dimension)
            gap = result.best - optimum
            table[result.method, result.problem, result.seed] = {
                "gap": gap,
                "cost": result.cost_adjoint,
                "reached": gap <= data_profiles.TOLERANCE * max(1.0, abs(optimum)),
            }
        problems = data_profiles.PROBLEM_NAMES
        summary = {
            name: {
                problem: {
                    "median_gap": median(table[name, problem, s]["gap"] for s in SEEDS),
                    "median_cost": median(
                        table[name, problem, s]["cost"] for s in SEEDS
                    ),
                    "reached": sum(table[name, problem, s]["reached"] for s in SEEDS),
                }
                for problem in problems
            }
            for name in (method, *BASELINES)
        }
        output["dimensions"][str(dimension)] = {
            "method": method,
            "summary": summary,
            "tests": compare(table, method, BASELINES, problems),
            "runs": [
                {"method": m, "problem": p, "seed": s, **values}
                for (m, p, s), values in sorted(table.items())
            ],
        }
        print(f"{dimension} variables: {len(results)} runs", flush=True)  # noqa: T201

    OUTPUT.write_text(json.dumps(output) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
