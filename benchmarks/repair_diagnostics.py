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
"""Measure what the adaptive repair leaves of the conditions it enforces.

The configuration compared with the baselines is run on the Rastrigin function,
whose global minimizer lies in a known box, and every master problem is
recorded. Its cuts, after the repair, are evaluated from the constraints of the
master problem itself:

- at every pair of solved boxes, the fraction of the conditions
  ``cut_i(alpha_j) <= v(alpha_j) - delta``, ``j != i``, still violated;
- at the box of the global minimizer, while it has not been solved, whether the
  lower envelope of the cuts exceeds the incumbent value, in which case the
  master problem cannot select this box.

    python -m benchmarks.repair_diagnostics
"""

from __future__ import annotations

import json
import logging
import warnings
from statistics import median

import numpy as np

from benchmarks import data_profiles
from benchmarks.run_statistics import COMPARED
from benchmarks.run_statistics import SEEDS

OUTPUT = data_profiles.OUTPUT.with_name("repair_diagnostics.json")
"""The file of the summaries."""

MARGIN_TOLERANCE = 1e-6
"""The tolerance with which a condition counts as satisfied."""


def _cut_values(problem, alpha: np.ndarray) -> list[float]:  # noqa: ANN001
    """Return the value of every objective cut at a box.

    Args:
        problem: The mixed-integer linear program.
        alpha: The one-hot vector of the box.

    Returns:
        The value of each cut, in the order of the constraints.
    """
    x = np.append(alpha, 0.0)
    return [
        float(np.ravel(c.evaluate(x))[0])
        for c in problem.constraints
        if c.name.startswith("objective outer approximation")
    ]


def _box(dimension: int, m: int, index: int) -> np.ndarray:
    """Return the one-hot vector of the box with the same index on every axis."""
    alpha = np.zeros(dimension * m)
    for j in range(dimension):
        alpha[j * m + index] = 1.0
    return alpha


def run_one(dimension: int, seed: int) -> dict:
    """Run the configuration on Rastrigin and measure its master problems.

    Args:
        dimension: The number of design variables.
        seed: The seed of the starting point.

    Returns:
        The fraction of violated conditions over all master problems, and the
        fraction of master problems excluding the box of the global minimizer.
    """
    from gemseo_bilevel_outer_approximation.algos.opt.core import (  # noqa: PLC0415
        outer_approximation_optimizer as core,
    )

    from benchmarks.data_profiles import _run  # noqa: PLC0415
    from benchmarks.problems import RASTRIGIN_LOWER_BOUND  # noqa: PLC0415

    m = 10
    # The global minimizer, the origin, lies in the interval of index 4.
    target = _box(dimension, m, int(-RASTRIGIN_LOWER_BOUND))
    counts = {"pairs": 0, "violated": 0, "masters": 0, "excluded": 0}
    original = core.OuterApproximationOptimizer._build_milp_problem

    def build(self, slopes_hist, alpha_hist, fopt_hist, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        problem = original(self, slopes_hist, alpha_hist, fopt_hist, *args, **kwargs)
        boxes = [np.asarray(a, float) for a in alpha_hist]
        values = list(fopt_hist)
        if len(boxes) >= 2:  # noqa: PLR2004
            delta = self.min_dfk
            at = [_cut_values(problem, a) for a in boxes]
            for j, row in enumerate(at):
                for i, cut in enumerate(row[: len(boxes)]):
                    if i != j:
                        counts["pairs"] += 1
                        if cut > values[j] - delta + MARGIN_TOLERANCE:
                            counts["violated"] += 1
            if not any(np.array_equal(a, target) for a in boxes):
                counts["masters"] += 1
                envelope = max(_cut_values(problem, target))
                if envelope > min(values) + MARGIN_TOLERANCE:
                    counts["excluded"] += 1
        return problem

    core.OuterApproximationOptimizer._build_milp_problem = build
    try:
        _run((COMPARED[dimension], "rastrigin", dimension, seed))
    finally:
        core.OuterApproximationOptimizer._build_milp_problem = original
    return {
        "violated": counts["violated"] / max(counts["pairs"], 1),
        "excluded": counts["excluded"] / max(counts["masters"], 1),
    }


def main() -> None:
    """Measure every starting point in both dimensions and write a summary."""
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    output = {}
    for dimension in data_profiles.DIMENSIONS:
        runs = [run_one(dimension, seed) for seed in SEEDS]
        output[str(dimension)] = {
            "median_violated": median(r["violated"] for r in runs),
            "max_violated": max(r["violated"] for r in runs),
            "median_excluded": median(r["excluded"] for r in runs),
            "max_excluded": max(r["excluded"] for r in runs),
            "runs": runs,
        }
        print(
            dimension, {k: v for k, v in output[str(dimension)].items() if k != "runs"}
        )  # noqa: T201
    OUTPUT.write_text(json.dumps(output, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
