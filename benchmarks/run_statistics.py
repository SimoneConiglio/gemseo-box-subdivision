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
"""Run the comparison with the baselines from twenty starting points.

The comparison of the data profiles, four problems in two and five variables, is
run from :data:`SEEDS`, twenty starting points whose first five are those of the
published profiles, so that every published run is one of these. The method is
used in the configuration compared with the baselines in both dimensions, swept
with ten subdivisions per variable.

With ``--variants``, the variants of the method, the challengers of this
configuration, are run from the same starting points, so that each is paired
with the configuration by starting point. The configuration is kept unless a
challenger is clearly better (see :mod:`benchmarks.statistics`).

Every run is kept, with its history, in ``benchmarks/.statistics/{n}.jsonl``,
one line per run appended as soon as it finishes, so that an interrupted study
resumes where it stopped. The runs are spread over every processor, each
single-threaded. The statistics are computed from these files by
:mod:`benchmarks.statistics`.

```shell
python -m benchmarks.run_statistics             # the method and the baselines
python -m benchmarks.run_statistics --variants  # the challengers
```
"""

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

from benchmarks import data_profiles

SEEDS = (*data_profiles.SEEDS, *range(505, 2000, 101))
"""The twenty seeds of the starting points, the published five first."""

COMPARED = {2: "swept", 5: "density_10"}
"""The configuration of the method compared with the baselines, by dimension."""

BASELINES = ("multistart", "cmaes", "direct", "tunneling", "egobox")
"""The baselines, EGO last in this list although the runner starts it first."""

CHALLENGERS = {
    dimension: tuple(
        name
        for name in (
            *data_profiles.VARIANTS[dimension],
            *data_profiles.LATE_VARIANTS[dimension],
        )
        if name != COMPARED[dimension]
    )
    for dimension in data_profiles.DIMENSIONS
}
"""The variants of the method compared with its configuration, by dimension."""

CACHE = Path(__file__).parent / ".statistics"
"""The directory keeping every finished run, one file per dimension."""


def main(arguments: list[str] | None = None) -> None:
    """Run every method on every problem from every starting point.

    Args:
        arguments: The command line arguments; ``--variants`` runs the
            challengers instead of the baselines.
            If ``None``, use those of the command line.
    """
    arguments = sys.argv[1:] if arguments is None else arguments
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    for dimension in data_profiles.DIMENSIONS:
        others = CHALLENGERS[dimension] if "--variants" in arguments else BASELINES
        results = data_profiles.collect(
            dimension,
            (COMPARED[dimension], *others),
            seeds=SEEDS,
            cache=CACHE / f"{dimension}.jsonl",
        )
        print(f"{dimension} variables: {len(results)} runs", flush=True)  # noqa: T201


if __name__ == "__main__":
    main()
