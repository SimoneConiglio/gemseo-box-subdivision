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
"""Run the method and the baselines in 10 and 20 variables, 500 per variable.

The budget grows with the dimension, $500$ equivalent evaluations per variable
as in two and five variables, i.e. $5000$ in 10 variables and $10000$ in 20,
unlike :mod:`benchmarks.run_dimensions`, whose budget is that of five variables
whatever the dimension. The methods are run on the four problems from the twenty
starting points of :mod:`benchmarks.run_statistics`:

- the swept configuration with ten subdivisions per variable (``density_10``),
  the reference, with eight and sixteen probes (``density_10_probes_8``,
  ``density_10_probes_16``), and with the default density (``swept``);
- the multistart algorithm, CMA-ES and IPOP-CMA-ES, DIRECT with and without its
  local bias, MLSL and the classic tunneling method.

Each run is made in a process of its own, as in
:mod:`benchmarks.run_dimensions`. The runs are kept in
``benchmarks/.statistics/scaled-{n}.jsonl``, the summary in
``docs/_static/dimensions_scaled.json``.

```shell
OMP_NUM_THREADS=1 python -m benchmarks.run_dimensions_scaled
```
"""

from __future__ import annotations

import json
import logging
import warnings

from benchmarks import data_profiles
from benchmarks import run_dimensions
from benchmarks.run_statistics import CACHE
from benchmarks.statistics import compare
from benchmarks.statistics import compare_areas

PER_VARIABLE = 500
"""The budget per design variable."""

METHODS = (
    "density_10",
    "density_10_probes_8",
    "density_10_probes_16",
    "swept",
    "multistart",
    "cmaes",
    "ipop_cmaes",
    "direct",
    "direct_global",
    "mlsl",
    "tunneling",
)
"""The methods, the reference first."""

REFERENCE = "density_10"
"""The method the others are compared with."""

OUTPUT = data_profiles.OUTPUT.with_name("dimensions_scaled.json")
"""The file of the summaries."""


def main() -> None:
    """Run every method in 10 and 20 variables and write the summaries."""
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    run_dimensions.METHODS = METHODS
    run_dimensions.ABORTS = CACHE / "scaled-aborts.json"
    output = {}
    for dimension in run_dimensions.DIMENSIONS:
        budget = PER_VARIABLE * dimension
        run_dimensions.BUDGET = budget
        cache = CACHE / f"scaled-{dimension}.jsonl"
        results = run_dimensions._collect(dimension, cache)  # noqa: SLF001
        print(f"{dimension} variables: {len(results)} runs", flush=True)  # noqa: T201
        targets = data_profiles.compute_targets(results)
        runs = [json.loads(line) for line in cache.read_text().splitlines()]
        table = run_dimensions._table(runs, targets, dimension)  # noqa: SLF001
        run_dimensions._add_aborts(table, dimension)  # noqa: SLF001
        problems = data_profiles.PROBLEM_NAMES
        others = tuple(m for m in METHODS if m != REFERENCE)
        output[str(dimension)] = {
            "budget": budget,
            "summary": run_dimensions._summary(table, METHODS),  # noqa: SLF001
            "tests": compare(table, REFERENCE, others, problems),
            "areas": compare_areas(table, REFERENCE, others, problems),
        }
        run_dimensions._print(output[str(dimension)], dimension)  # noqa: SLF001
        OUTPUT.write_text(json.dumps(output, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
