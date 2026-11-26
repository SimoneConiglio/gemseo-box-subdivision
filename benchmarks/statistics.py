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

The variants of the method, run by ``python -m benchmarks.run_statistics
--variants``, are compared with the configuration in the same way, the Holm
correction running over the problems and the variants of each dimension. The
configuration was fixed before these runs, and a variant replaces it only if it
is clearly better: it succeeds significantly more often on some problem, or has
a larger area with an interval excluding zero, and succeeds significantly less
often on none (:func:`clearly_better`). A variant selected this way would be
compared with the baselines on new starting points, the present ones having
served to select it.

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
from benchmarks.run_statistics import CHALLENGERS
from benchmarks.run_statistics import COMPARED
from benchmarks.run_statistics import SEEDS

OUTPUT = data_profiles.OUTPUT.with_name("statistics.json")
"""The file the per-run results and the statistics are written to."""

SIGNIFICANCE = 0.05
"""The level below which a corrected p-value is significant."""

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


def compare(
    table: dict[tuple[str, str, int], dict],
    method: str,
    others: tuple[str, ...],
    problems: tuple[str, ...],
) -> list[dict]:
    """Compare a method with others, problem by problem, paired by starting point.

    Args:
        table: The outcome of each run, by method, problem and seed.
        method: The method.
        others: The methods it is compared with.
        problems: The problems.

    Returns:
        The tests, their p-values corrected by Holm over all of them.
    """
    tests = []
    for other in others:
        for problem in problems:
            ours = [table[method, problem, seed] for seed in SEEDS]
            theirs = [table[other, problem, seed] for seed in SEEDS]
            only_ours, only_theirs, p_success = mcnemar(
                [r["reached"] for r in ours], [r["reached"] for r in theirs]
            )
            tests.append({
                "baseline": other,
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
    return tests


def compare_areas(
    table: dict[tuple[str, str, int], dict],
    method: str,
    others: tuple[str, ...],
    problems: tuple[str, ...],
) -> list[dict]:
    """Compare the area of a method with those of others, with bootstrap intervals.

    Args:
        table: The outcome of each run, by method, problem and seed.
        method: The method.
        others: The methods it is compared with.
        problems: The problems.

    Returns:
        The areas and the difference with each other method.
    """
    rng = default_rng(0)
    samples = rng.integers(0, len(SEEDS), size=(N_BOOTSTRAP, len(SEEDS)))
    areas = {
        name: array([
            mean([table[name, problem, seed]["area"] for problem in problems])
            for seed in SEEDS
        ])
        for name in (method, *others)
    }
    area_tests = []
    for other in others:
        difference = areas[method] - areas[other]
        boot = difference[samples].mean(axis=1)
        area_tests.append({
            "baseline": other,
            "area_method": float(areas[method].mean()),
            "area_baseline": float(areas[other].mean()),
            "difference": float(difference.mean()),
            "ci95": [float(percentile(boot, 2.5)), float(percentile(boot, 97.5))],
        })
    return area_tests


def clearly_better(tests: list[dict], area_test: dict) -> bool:
    """Return whether a challenger is clearly better than the configuration.

    The tests compare the configuration with the challenger, so that the
    challenger is clearly better when it succeeds significantly more often on
    some problem and significantly less often on none, or when its area is
    larger with an interval excluding zero and its success is significantly
    lower on no problem.

    Args:
        tests: The tests of the configuration against the challenger.
        area_test: The area test of the configuration against the challenger.

    Returns:
        Whether the challenger is clearly better.
    """
    significant = [t for t in tests if t["p_success_holm"] < SIGNIFICANCE]
    better = any(t["only_baseline"] > t["only_method"] for t in significant)
    worse = any(t["only_method"] > t["only_baseline"] for t in significant)
    return not worse and (better or area_test["ci95"][1] < 0)


def main() -> None:
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

        problems = data_profiles.PROBLEM_NAMES
        tests = compare(table, method, BASELINES, problems)
        area_tests = compare_areas(table, method, AREA_BASELINES, problems)
        entry = {"method": method, "tests": tests, "areas": area_tests}
        _print(dimension, tests, area_tests)
        complete = {
            name
            for name in CHALLENGERS[dimension]
            if all((name, p, s) in table for p in problems for s in SEEDS)
        }
        challengers = tuple(n for n in CHALLENGERS[dimension] if n in complete)
        if challengers:
            variant_tests = compare(table, method, challengers, problems)
            variant_areas = compare_areas(table, method, challengers, problems)
            entry["variants"] = {
                "tests": variant_tests,
                "areas": variant_areas,
                "clearly_better": [
                    area["baseline"]
                    for area in variant_areas
                    if clearly_better(
                        [t for t in variant_tests if t["baseline"] == area["baseline"]],
                        area,
                    )
                ],
            }
            _print(dimension, variant_tests, variant_areas)
            print("clearly better:", entry["variants"]["clearly_better"])  # noqa: T201

        methods = {method, *BASELINES, *challengers}
        entry["runs"] = [
            {"method": m, "problem": p, "seed": s, **values}
            for (m, p, s), values in sorted(table.items())
            if m in methods and s in SEEDS
        ]
        output["dimensions"][str(dimension)] = entry

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
