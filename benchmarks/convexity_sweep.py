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
r"""Sweeping the convexity setting in parallel, rather than calibrating it.

The standing criticism of the method is that the convexity margin ``min_dfk``
and the convexification constant are absolute quantities in the units of the
objective: a margin of $100$ reaches the optimum from every starting point on
Rastrigin, which spans about eighty, and the same margin is the worst of those
tried on Ackley, which spans about twenty-two. The user is asked for a number
calibrated against a quantity they do not know.

The master already avoids that question for its trust region: it probes one
radius per parallel point, over ``geomspace(step / 2, step)``, so the parallel
points are a **sweep** and not a batch. The same probes can carry a ladder of
convexity values:

- probe $k$ of an iteration solves the master at rung $k$ of a ladder of
  convexity values, so one iteration spans the ladder rather than repeating one
  value. The low rungs leave the cuts near their raw slopes and propose boxes
  near the incumbent, the high rungs let every unexplored box outrank it: **one
  iteration yields both the exploitation and the exploration**;
- a probe that proposes a box already solved is **redeployed one rung up**, and
  again, until it proposes a new box or the ladder is exhausted. Exhaustion at
  every probe says that no value up to $\kappa_{\max}$ proposes anything new,
  which is a stronger reason to stop than a single value not proposing anything;
- the user supplies an upper bound, or nothing at all, the bound then being
  read off the spread of the objective over the boxes already solved. The number
  of rungs is never asked for: it is the number of parallel points the master
  probes with, since a rung with no probe to carry it is never solved.

A redeployment costs one more mixed-integer solve and **no objective
evaluation**, which is the currency the benchmark counts: escalating is nearly
free in the cost this method is measured on.

A probe per rung is the whole construction, so the sweep needs
``number_of_parallel_points`` above one. With a single probe there is no ladder
to span and the top rung is used, the conservative end, rather than leaving a run
with its cuts unguarded.

**That loop belongs to the master, and it lives there**, under the settings
``convexity_sweep_points`` and ``convexity_sweep_max``. Where the installed
master has them, this module only passes them and measures. Where it does not,
see `MASTER_SWEEPS_CONVEXITY`, the package itself drives the released master from
outside, by patching :meth:`.OuterApproximationOptimizer._solve_milp`, the same
idiom as `benchmarks/trust_region.py`. That driver lives in the package and not
here, since a swept run has to sweep wherever it is run from and not only under
the benchmark; this module only opens it, so that the measurement below is
reproducible against either master. The driver goes when the master ships the
sweep.

```shell
python -m benchmarks.convexity_sweep
```
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextlib import suppress
from statistics import median
from typing import TYPE_CHECKING
from typing import Any

from gemseo_bilevel_outer_approximation.algos.opt.core import (
    outer_approximation_optimizer as core,
)

from benchmarks.baselines import run_box_subdivision
from benchmarks.configurations import ADAPTIVE
from benchmarks.configurations import TRUST_REGION_RADIUS
from benchmarks.problems import PROBLEMS
from gemseo_box_subdivision import SweptBoxSubdivisionSettings
from gemseo_box_subdivision import convexity_sweep as policy
from gemseo_box_subdivision._convexity_sweep_driver import Deployment
from gemseo_box_subdivision._convexity_sweep_driver import drive_the_sweep
from gemseo_box_subdivision.convexity_sweep import HEADROOM
from gemseo_box_subdivision.convexity_sweep import MASTER_SWEEPS_CONVEXITY

if TYPE_CHECKING:
    from collections.abc import Iterator


DIMENSION = 2
"""The number of design variables."""

BUDGET = 1000
"""The budget in equivalent objective evaluations."""

SEEDS = (11, 101, 202, 303, 404, 505)
"""The seeds of the starting points."""

N_SUBDIVISIONS = 10
"""The number of subdivisions per variable."""

TOLERANCE = 1e-3
"""The distance to the global minimum under which it counts as reached."""


@contextmanager
def set_headroom(factor: float) -> Iterator[None]:
    """Set the factor lifting an upper bound read off the objective.

    The headroom is a constant of the sweep rather than a setting of a run, so
    changing it to measure what it buys means changing the constant. Where the
    master sweeps on its own it reads the name it imported, and where the stub
    does the sweeping it is this package's copy that is read.

    Args:
        factor: The factor to apply while the context is open.

    Yields:
        Nothing.
    """
    modules = [policy]
    if MASTER_SWEEPS_CONVEXITY:
        # The master imported the name, so its own binding is the one it reads.
        modules.append(core)

    originals = [module.HEADROOM for module in modules]
    for module in modules:
        module.HEADROOM = factor

    try:
        yield
    finally:
        for module, original in zip(modules, originals, strict=False):
            module.HEADROOM = original


@contextmanager
def convexity_sweep(
    max_value: float | None,
) -> Iterator[tuple[dict[str, Any], list[Deployment]]]:
    """Ask for a sweep of the convexity, of whichever master is installed.

    Args:
        max_value: The upper bound of the sweep, zero to read it off the
            objective, or ``None`` for a fixed margin and no sweep at all.

    Yields:
        The settings to add to those of the master, and the deployments of the
        stub, which is empty when the master sweeps on its own and keeps no
        such record.
    """
    if max_value is None:
        yield {}, []
        return

    if MASTER_SWEEPS_CONVEXITY:
        # The rungs are the probes, which the master knows; only the bound is
        # asked of it, a bound of zero being the one it reads off the objective.
        yield (
            {
                "convexity_sweep_max": max_value,
                "convexity_sweep_points": ADAPTIVE["number_of_parallel_points"],
            },
            [],
        )
        return

    # The swept entry point is what the driver takes, and what this measures.
    with drive_the_sweep(SweptBoxSubdivisionSettings(max_value=max_value)) as trace:
        yield {}, trace


def run(
    problem: Any,
    seed: int,
    sweep: float | None,
    margin: float,
    headroom: float = HEADROOM,
) -> tuple[Any, list[Deployment]]:
    """Run the method with a swept convexity margin, or with a fixed one.

    Args:
        problem: The problem.
        seed: The seed of the starting point.
        sweep: The upper bound of the sweep, zero to read it off the objective,
            or ``None`` for a fixed margin.
        margin: The margin given to the mechanism. A swept run is given none,
            the point of the sweep being that the user has none to give.
        headroom: The factor lifting an upper bound read off the objective.

    Returns:
        The outcome of the run, and the deployments of the sweep.
    """
    with set_headroom(headroom), convexity_sweep(sweep) as (settings, trace):
        outcome = run_box_subdivision(
            problem,
            DIMENSION,
            seed,
            BUDGET,
            adjoint=True,
            n_subdivisions=N_SUBDIVISIONS,
            overrides={
                "min_dfk": margin,
                "max_step": TRUST_REGION_RADIUS,
                **settings,
            },
        )

    return outcome, trace


SETUPS = (
    ("fixed, margin 1", None, 1.0, HEADROOM),
    ("fixed, margin 10", None, 10.0, HEADROOM),
    ("fixed, margin 100", None, 100.0, HEADROOM),
    ("sweep, max 100", 100.0, 0.0, HEADROOM),
    ("sweep, max 1000", 1000.0, 0.0, HEADROOM),
    ("sweep, observed", 0.0, 0.0, 1.0),
    ("sweep, observed x 10", 0.0, 0.0, 10.0),
)
"""The configurations compared, the fixed margins against the sweeps.

The fixed margins are the sweep's own range, one rung at a time, which is what a
user calibrating the setting has to search by hand. The sweeps are given an upper
bound that is right, one that is ten times too large, and two that are read off
the spread of the objective over the boxes already solved, with and without the
headroom that spread needs: it is a lower estimate of the spread over the design
space, and badly so in the first iterations.

**A swept run is given no margin at all**, which is the point: the mechanism
falls back on that value only until enough boxes are solved for a ladder to
exist.
"""

PROBLEM_NAMES = ("rastrigin", "ackley")
"""The two problems, whose objectives are on different scales.

Rastrigin spans about eighty over its design space and Ackley about twenty-two,
and the tuning reports that the margin reaching the optimum on the first is the
worst of those tried on the second. One setting has to serve both, or it has not
answered the criticism.
"""


def main() -> None:
    """Compare the sweep against the fixed margins it replaces."""
    logging.disable(logging.CRITICAL)
    swept_by = "the master" if MASTER_SWEEPS_CONVEXITY else "the stub"
    print(
        f"{DIMENSION} variables, {N_SUBDIVISIONS} subdivisions, budget {BUDGET}, "
        f"over {len(SEEDS)} starting points, swept by {swept_by}\n"
    )
    print(
        f"{'problem':>10} {'convexity':>26} {'gap':>9} {'cost':>7} {'reached':>8}"
        f" {'rungs':>7}"
    )
    for name in PROBLEM_NAMES:
        benchmark = PROBLEMS[name]
        optimum = benchmark.optimum(DIMENSION)
        for label, sweep, margin, headroom in SETUPS:
            gaps = []
            costs = []
            escalated = 0
            deployed = 0
            for seed in SEEDS:
                with suppress(Exception):
                    outcome, trace = run(benchmark, seed, sweep, margin, headroom)
                    gaps.append(outcome.gap(optimum))
                    costs.append(outcome.cost_adjoint)
                    deployed += len(trace)
                    escalated += sum(one.escalated for one in trace)

            if not gaps:
                print(f"{name:>10} {label:>26} {'failed':>9}")
                continue

            share = f"{escalated / deployed:>6.0%}" if deployed else "     -"
            print(
                f"{name:>10} {label:>26} {median(gaps):>9.3f} {median(costs):>7.0f}"
                f" {sum(gap <= TOLERANCE for gap in gaps)}/{len(gaps):<6}"
                f" {share}"
            )

    logging.disable(logging.NOTSET)


if __name__ == "__main__":
    main()
