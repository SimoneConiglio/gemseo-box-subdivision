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
"""Rerun a run aborted by CBC, with SCIP solving the master problems.

CBC, which the MILP solver of the bilevel plugin creates through OR-Tools,
aborts in C++ on some of the larger master problems, with ten subdivisions per
variable in ten dimensions; the abort cannot be caught and kills the run. The
same run, made again, aborts at the same master problem. This script makes it
with SCIP, which OR-Tools also bundles, as master solver, everything else being
unchanged, and appends it to a cache of runs.

```shell
OMP_NUM_THREADS=1 python -m benchmarks.rerun_with_scip \
    10 density_10 griewank 505 5000 benchmarks/.statistics/scaled-10.jsonl
```
"""

from __future__ import annotations

import sys
from pathlib import Path

from gemseo_bilevel_outer_approximation.algos.opt.ortools_milp import ortools_milp
from ortools.linear_solver import pywraplp


class _Solver:
    """Forward to :class:`pywraplp.Solver`, but create SCIP solvers."""

    def __getattr__(self, name: str):  # noqa: ANN204
        return getattr(pywraplp.Solver, name)

    def __call__(self, name: str, problem_type: int) -> pywraplp.Solver:  # noqa: ARG002
        solver = pywraplp.Solver.CreateSolver("SCIP")
        if solver is None:
            msg = "SCIP is not available in OR-Tools."
            raise RuntimeError(msg)
        return solver


class _Module:
    """Forward to :mod:`pywraplp`, with :class:`_Solver` as solver."""

    Solver = _Solver()

    def __getattr__(self, name: str):  # noqa: ANN204
        return getattr(pywraplp, name)


def main() -> None:
    """Make the run given on the command line with SCIP as master solver."""
    ortools_milp.pywraplp = _Module()
    from benchmarks import data_profiles  # noqa: PLC0415

    dimension, method, problem, seed, budget, cache = sys.argv[1:]
    data_profiles.collect(
        int(dimension),
        (method,),
        problem_names=(problem,),
        seeds=(int(seed),),
        max_workers=1,
        cache=Path(cache),
        budget=int(budget),
    )


if __name__ == "__main__":
    main()
