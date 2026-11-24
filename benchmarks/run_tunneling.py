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
"""Run the tunneling baseline under the protocols of the published tables.

Two protocols, those of the comparison with the baselines:

- that of the data profiles, four problems, two and five variables, five
  starting points and $500$ equivalent evaluations per variable;
- that of :mod:`benchmarks.small_budget`, the same problems, three starting
  points and $500$ evaluations.

The data profile of the first is computed against the **published** targets of
``docs/_static/data_profiles.json``, read rather than regenerated: the targets
are generated from the pooled histories of every method, so that adding a method
to the pool would move every published number. The fraction of the targets a
method reaches depends only on its own runs and on the targets, so the profile
so computed is comparable with the published ones. As a check of that claim, the
deterministic DIRECT is run again and its area compared with the published one.

Besides the settings of :data:`benchmarks.tunneling.SETTINGS`, which stop at the
budget, the method is run with its own stopping rule, which ends a run once two
tunneling searches per variable have failed from the same minimizer.

The runs are serial, the counters not seeing evaluations made in other
processes, and take a few minutes:

```shell
python -m benchmarks.run_tunneling
```
"""

from __future__ import annotations

import json
import logging
import time
import warnings
from dataclasses import replace
from statistics import median
from typing import TYPE_CHECKING

from benchmarks import data_profiles
from benchmarks.baselines import run
from benchmarks.baselines import run_tunneling
from benchmarks.problems import PROBLEMS
from benchmarks.tunneling import SETTINGS
from benchmarks.tunneling import TunnelingSettings

if TYPE_CHECKING:
    from benchmarks.baselines import Result

SMALL_BUDGET = 500
"""The budget of the comparison at a small budget."""

SMALL_BUDGET_SEEDS = (11, 101, 202)
"""The starting points of the comparison at a small budget."""

VARIANTS = {
    "tunneling": SETTINGS,
    "tunneling_2n_attempts": TunnelingSettings(attempts_per_variable=2),
}
"""The settings run: those of the benchmark, which stop at the budget, and the
method's own stopping rule after two failed tunneling searches per variable,
reported as a sensitivity check rather than chosen from the results."""


def _row(name: str, dimension: int, results, seconds: float) -> str:  # noqa: ANN001
    """Return a row of a table: median gap, median cost, runs reaching it.

    Args:
        name: The name of the problem.
        dimension: The number of design variables.
        results: The outcome of the runs.
        seconds: The wall-clock time of the runs.

    Returns:
        The row.
    """
    optimum = PROBLEMS[name].optimum(dimension)
    gaps = [result.gap(optimum) for result in results]
    tolerance = data_profiles.TOLERANCE * max(1.0, abs(optimum))
    reached = sum(gap <= tolerance for gap in gaps)
    costs = [result.cost_adjoint for result in results]
    truncated = sum(result.truncated for result in results)
    return (
        f"{name:>17} {dimension:>2} {median(gaps):>9.4f} {median(costs):>6.0f}"
        f" {reached}/{len(gaps)} {truncated:>9} {seconds:>8.1f}"
    )


def main() -> None:
    """Run both protocols and print their tables and the data profiles."""
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    published = json.loads(data_profiles.OUTPUT.read_text(encoding="utf-8"))
    header = (
        f"{'problem':>17} {'n':>2} {'gap':>9} {'cost':>6} reached truncated"
        f" {'seconds':>8}"
    )
    for title, seeds, budget_of in (
        (
            "500 equivalent evaluations per variable, 5 starting points",
            data_profiles.SEEDS,
            lambda dimension: data_profiles.BUDGET_PER_VARIABLE * dimension,
        ),
        (
            f"{SMALL_BUDGET} equivalent evaluations, 3 starting points",
            SMALL_BUDGET_SEEDS,
            lambda dimension: SMALL_BUDGET,  # noqa: ARG005
        ),
    ):
        for dimension in data_profiles.DIMENSIONS:
            results = []
            for method, settings in VARIANTS.items():
                print(f"\n{method}, {title}\n{header}", flush=True)  # noqa: T201
                for name in data_profiles.PROBLEM_NAMES:
                    start = time.perf_counter()
                    runs = [
                        replace(
                            run_tunneling(
                                PROBLEMS[name],
                                dimension,
                                seed,
                                budget_of(dimension),
                                True,
                                settings,
                            ),
                            method=method,
                        )
                        for seed in seeds
                    ]
                    seconds = time.perf_counter() - start
                    results.extend(runs)
                    print(_row(name, dimension, runs, seconds), flush=True)  # noqa: T201

            if seeds == data_profiles.SEEDS:
                _print_profiles(published, dimension, results)

    logging.disable(logging.NOTSET)


def _print_profiles(published: dict, dimension: int, results: list[Result]) -> None:
    """Print the data profiles against the published targets.

    Args:
        published: The published data profiles.
        dimension: The number of design variables.
        results: The outcome of the runs of the tunneling variants.
    """
    data = published["dimensions"][str(dimension)]
    budget = data["budget"]
    direct = [
        run("direct", PROBLEMS[name], dimension, seed, budget)
        for name in data_profiles.PROBLEM_NAMES
        for seed in data_profiles.SEEDS
    ]
    profiles = data_profiles.compute_profiles([*results, *direct], data["targets"])
    checkpoints = [budget // 10, budget // 4, budget // 2, budget]
    print(  # noqa: T201
        f"\ndata profile, {dimension} variables, published targets\n"
        f"{'':>22} {'area':>5} " + " ".join(f"{c:>5}" for c in checkpoints)
    )
    for method in (*VARIANTS, "direct"):
        profile = data_profiles._padded(profiles[method], budget)
        cells = " ".join(f"{profile[c - 1]:>5.0%}" for c in checkpoints)
        print(  # noqa: T201
            f"{method:>22} {data_profiles.area(profile, budget):>5.2f} {cells}"
        )
    print(f"{'direct, published':>22} {data['areas']['direct']:>5.2f}")  # noqa: T201


if __name__ == "__main__":
    main()
