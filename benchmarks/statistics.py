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
r"""Paired statistics of the comparison with the baselines, twenty starting points.

Reads the runs of :mod:`benchmarks.run_statistics` and compares the method with
each baseline, every run of one being paired with the run of the other from the
same starting point. Two measures are kept, fixed before the runs were made:

Final distance to the optimum, the primary measure
: On each problem, the success, a distance below the tolerance of the
  benchmark, is compared by the exact McNemar test, a binomial test on the
  starting points where exactly one of the two methods succeeds, and the
  distance itself by the Wilcoxon signed-rank test. The $p$-values of each
  dimension are corrected by the Holm procedure over its problems and baselines.

Area under the data profile, the secondary measure
: The profile of a set of runs is the mean, over the runs, of the fraction of
  the targets of its problem each run has reached after each evaluation, so
  that its area is the mean of the areas of the runs. The areas are computed
  against the **published** targets of ``docs/_static/data_profiles.json``, and
  the difference with each baseline, over the four problems, is given with a
  $95\%$ confidence interval from a bootstrap over the starting points, paired
  across methods. EGO, whose budget is $500$ evaluations, is left out of it.

The per-run results, with the history of the best value at the evaluations where
it improves, are written to ``docs/_static/statistics.json``.

```shell
python -m benchmarks.statistics
```
"""

from __future__ import annotations

import json
from itertools import pairwise
from statistics import median

from numpy import array
from numpy import mean
from numpy import percentile
from numpy.random import default_rng
from scipy.stats import binomtest
from scipy.stats import wilcoxon

from benchmarks import data_profiles
from benchmarks.problems import PROBLEMS
from benchmarks.run_statistics import BASELINES
from benchmarks.run_statistics import CACHE
from benchmarks.run_statistics import COMPARED
from benchmarks.run_statistics import SEEDS

OUTPUT = data_profiles.OUTPUT.with_name("statistics.json")
"""The file the per-run results and the statistics are written to."""

N_BOOTSTRAP = 10_000
"""The number of bootstrap samples of the starting points."""

AREA_BASELINES = tuple(name for name in BASELINES if name != "egobox")
"""The baselines whose budget is that of the method, compared by area."""


def run_area(history: list[float], targets: list[float], budget: int) -> float:
    """Return the area of the profile of one run.

    Args:
        history: The best value after each equivalent evaluation.
        targets: The target values of the problem.
        budget: The budget.

    Returns:
        The mean, over the evaluations of the budget, of the fraction of the
        targets reached.
    """
    padded = data_profiles._padded(history, budget)
    return float(mean([sum(v <= t for t in targets) / len(targets) for v in padded]))


def change_points(history: list[float]) -> list[list[float]]:
    """Return the evaluations at which the best value improves, and the value.

    Args:
        history: The best value after each equivalent evaluation.

    Returns:
        The evaluation, counted from one, and the best value at each change.
    """
    points = [[1, history[0]]] if history else []
    for index, (before, after) in enumerate(pairwise(history), start=2):
        if after < before:
            points.append([index, after])
    return points


def holm(p_values: list[float]) -> list[float]:
    """Return the p-values corrected by the Holm procedure.

    Args:
        p_values: The p-values of a family of tests.

    Returns:
        The corrected p-values, in the same order.
    """
    order = sorted(range(len(p_values)), key=p_values.__getitem__)
    corrected = [0.0] * len(p_values)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[index]))
        corrected[index] = running
    return corrected


def mcnemar(first: list[bool], second: list[bool]) -> tuple[int, int, float]:
    """Return the exact McNemar test of two paired lists of successes.

    Args:
        first: Whether each run of the first method succeeds.
        second: Whether the run of the second method from the same start does.

    Returns:
        The starting points where only the first succeeds, those where only the
        second does, and the two-sided p-value.
    """
    only_first = sum(a and not b for a, b in zip(first, second, strict=True))
    only_second = sum(b and not a for a, b in zip(first, second, strict=True))
    if only_first + only_second == 0:
        return 0, 0, 1.0
    return (
        only_first,
        only_second,
        float(binomtest(only_first, only_first + only_second).pvalue),
    )


def signed_rank(first: list[float], second: list[float]) -> float:
    """Return the p-value of the Wilcoxon signed-rank test on paired distances.

    Args:
        first: The distances of the first method.
        second: The distances of the second method from the same starts.

    Returns:
        The two-sided p-value, one when all the differences vanish.
    """
    differences = [a - b for a, b in zip(first, second, strict=True)]
    if all(abs(d) <= 1e-12 for d in differences):
        return 1.0
    return float(wilcoxon(first, second, zero_method="zsplit").pvalue)


def main() -> None:  # noqa: PLR0914
    """Compute and write the statistics of both dimensions."""
    published = json.loads(data_profiles.OUTPUT.read_text(encoding="utf-8"))
    output = {"seeds": list(SEEDS), "dimensions": {}}
    for dimension in data_profiles.DIMENSIONS:
        runs = [
            json.loads(line)
            for line in (CACHE / f"{dimension}.jsonl").read_text().splitlines()
        ]
        targets = published["dimensions"][str(dimension)]["targets"]
        method = COMPARED[dimension]
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

        methods = (method, *BASELINES)
        problems = data_profiles.PROBLEM_NAMES
        tests = []
        for baseline in BASELINES:
            for problem in problems:
                ours = [table[method, problem, seed] for seed in SEEDS]
                theirs = [table[baseline, problem, seed] for seed in SEEDS]
                only_ours, only_theirs, p_success = mcnemar(
                    [r["reached"] for r in ours], [r["reached"] for r in theirs]
                )
                tests.append({
                    "baseline": baseline,
                    "problem": problem,
                    "reached": [
                        sum(r["reached"] for r in ours),
                        sum(r["reached"] for r in theirs),
                    ],
                    "median_gap": [
                        median(r["gap"] for r in ours),
                        median(r["gap"] for r in theirs),
                    ],
                    "only_method": only_ours,
                    "only_baseline": only_theirs,
                    "p_success": p_success,
                    "p_gap": signed_rank(
                        [r["gap"] for r in ours], [r["gap"] for r in theirs]
                    ),
                })

        for key in ("p_success", "p_gap"):
            for test, corrected in zip(
                tests, holm([test[key] for test in tests]), strict=True
            ):
                test[f"{key}_holm"] = corrected

        rng = default_rng(0)
        samples = rng.integers(0, len(SEEDS), size=(N_BOOTSTRAP, len(SEEDS)))
        areas = {}
        for name in (method, *AREA_BASELINES):
            per_seed = array([
                mean([table[name, problem, seed]["area"] for problem in problems])
                for seed in SEEDS
            ])
            areas[name] = per_seed
        area_tests = []
        for baseline in AREA_BASELINES:
            difference = areas[method] - areas[baseline]
            boot = difference[samples].mean(axis=1)
            area_tests.append({
                "baseline": baseline,
                "area_method": float(areas[method].mean()),
                "area_baseline": float(areas[baseline].mean()),
                "difference": float(difference.mean()),
                "ci95": [float(percentile(boot, 2.5)), float(percentile(boot, 97.5))],
            })

        output["dimensions"][str(dimension)] = {
            "method": method,
            "tests": tests,
            "areas": area_tests,
            "runs": [
                {"method": m, "problem": p, "seed": s, **values}
                for (m, p, s), values in sorted(table.items())
                if m in methods
            ],
        }
        _print(dimension, tests, area_tests)

    OUTPUT.write_text(json.dumps(output) + "\n", encoding="utf-8")


def _print(dimension: int, tests: list[dict], area_tests: list[dict]) -> None:
    """Print the tests of one dimension.

    Args:
        dimension: The number of design variables.
        tests: The tests of the final distance.
        area_tests: The tests of the area.
    """
    print(f"\n{dimension} variables, {len(SEEDS)} starting points")  # noqa: T201
    print(  # noqa: T201
        f"{'baseline':>10} {'problem':>15} {'reached':>9} {'only':>7}"
        f" {'p succ':>7} {'Holm':>6} {'p gap':>7} {'Holm':>6}"
    )
    for t in tests:
        print(  # noqa: T201
            f"{t['baseline']:>10} {t['problem']:>15}"
            f" {t['reached'][0]:>3}/{t['reached'][1]:<4}"
            f" {t['only_method']:>3}/{t['only_baseline']:<3}"
            f" {t['p_success']:>7.4f} {t['p_success_holm']:>6.3f}"
            f" {t['p_gap']:>7.4f} {t['p_gap_holm']:>6.3f}"
        )
    for t in area_tests:
        print(  # noqa: T201
            f"area {t['baseline']:>10}: {t['area_method']:.3f} vs"
            f" {t['area_baseline']:.3f}, difference {t['difference']:+.3f}"
            f" [{t['ci95'][0]:+.3f}, {t['ci95'][1]:+.3f}]"
        )


if __name__ == "__main__":
    main()
