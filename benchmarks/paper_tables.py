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
r"""Every remaining table of the paper, from the twenty starting points.

The tables of the method's own studies (enumeration, density, proposed density,
swept convexity, tuning of the master and extensions) were first measured from
three to eight starting points each. This reruns each of their cells from the
twenty starting points of :mod:`benchmarks.run_statistics`, with the run
function of the study that defined it, so that every table of the paper rests
on the same starting points. A run is counted as reaching the optimum within
:data:`benchmarks.data_profiles.TOLERANCE`, as in the comparison with the
baselines.

The two-dimensional tuning of the master was first measured on a harness of its
own; its cells are now runs of :func:`benchmarks.baselines.run_box_subdivision`
on the Rastrigin problem of the benchmark, ten subdivisions per variable and
$1000$ evaluations, like every other two-dimensional study.

Every run is appended to ``benchmarks/.statistics/tables.jsonl`` as soon as it
ends, so that an interrupted study resumes, and the summary of every cell, its
median distance, median cost and number of starting points reaching the
optimum, is written to ``docs/_static/paper_tables.json``.

```shell
OMP_NUM_THREADS=1 python -m benchmarks.paper_tables [table ...]
```
"""

from __future__ import annotations

import json
import logging
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import as_completed
from statistics import median
from typing import Any

from benchmarks import data_profiles
from benchmarks.problems import PROBLEMS
from benchmarks.run_statistics import CACHE
from benchmarks.run_statistics import SEEDS

OUTPUT = data_profiles.OUTPUT.with_name("paper_tables.json")
"""The file the summary of every cell is written to."""

RUNS = CACHE / "tables.jsonl"
"""The file keeping every finished run."""

ESTIMATED = {
    "rastrigin": (10,) * 5,
    "styblinski_tang": (2,) * 5,
    "partly_multimodal": (10, 10, 1, 1, 1),
    "griewank": (19, 13, 11, 7, 9),
    "ackley": (63,) * 5,
}
"""The densities proposed by the basin count, which is deterministic."""

HEADROOM = 4
"""The budget of a run at an estimated density, in predicted costs."""

COST_PER_SUB_PROBLEM = 40
"""The predicted cost of a sub-problem, in equivalent evaluations."""


def _estimated_budget(density: tuple[int, ...]) -> int:
    """Return the budget granted to a run at an estimated density.

    Args:
        density: The number of subdivisions of each variable.

    Returns:
        The budget.
    """
    return HEADROOM * COST_PER_SUB_PROBLEM * sum(density)


def _cell(table, row, problem, dimension, budget, runner, **settings) -> dict:  # noqa: ANN001, PLR0913
    """Return the definition of a cell.

    Args:
        table: The label of the table.
        row: The row of the cell.
        problem: The name of the problem.
        dimension: The number of design variables.
        budget: The budget.
        runner: The name of the run function.
        **settings: The settings of the run function.

    Returns:
        The definition of the cell.
    """
    return {
        "table": table,
        "row": row,
        "problem": problem,
        "dimension": dimension,
        "budget": budget,
        "runner": runner,
        "settings": settings,
    }


def cells() -> list[dict]:  # noqa: C901, PLR0912
    """Return every cell of the tables, in the order of the paper.

    Returns:
        The definition of each cell.
    """
    four = ("rastrigin", "ackley", "styblinski_tang", "griewank")
    defined = [_cell("enum", "enumeration", "rastrigin", 2, 0, "enumeration")]
    defined.append(_cell("enum", "outer approximation", "rastrigin", 2, 0, "oa"))
    for m in (2, 4, 10, 16, 24):
        defined.extend(
            _cell("density", m, name, 5, 2500, "box", n_subdivisions=m) for name in four
        )
    for name, density in ESTIMATED.items():
        budget = _estimated_budget(density)
        defined.extend((
            _cell(
                "proposed", "calibrated", name, 5, budget, "density", density=density
            ),
            _cell(
                "proposed", "swept", name, 5, budget, "swept_density", density=density
            ),
        ))
    budget = _estimated_budget((10,) * 5)
    defined.extend((
        _cell(
            "proposed",
            "calibrated, 10",
            "ackley",
            5,
            budget,
            "density",
            density=(10,) * 5,
        ),
        _cell(
            "proposed",
            "swept, 10",
            "ackley",
            5,
            budget,
            "swept_density",
            density=(10,) * 5,
        ),
    ))
    for label, sweep, margin, headroom in (
        ("fixed, margin 10", None, 10.0, 4.0),
        ("fixed, margin 100", None, 100.0, 4.0),
        ("sweep, max 100", 100.0, 0.0, 4.0),
        ("sweep, unbounded", 0.0, 0.0, 4.0),
    ):
        defined.extend(
            _cell(
                "sweep",
                label,
                name,
                2,
                1000,
                "sweep",
                sweep=sweep,
                margin=margin,
                headroom=headroom,
            )
            for name in ("rastrigin", "ackley")
        )
    for points in (1, 4, 8):
        defined.extend(
            _cell(
                "margin",
                f"{points}, {margin:g}",
                "rastrigin",
                2,
                1000,
                "box",
                n_subdivisions=10,
                overrides={"min_dfk": margin, "number_of_parallel_points": points},
            )
            for margin in (1.0, 10.0, 30.0, 100.0, 300.0)
        )
    defined.extend(
        _cell(
            "margin-ackley",
            margin,
            "ackley",
            5,
            2500,
            "box",
            n_subdivisions=10,
            overrides={"min_dfk": margin},
        )
        for margin in (100.0, 30.0, 10.0, 3.0, 1.0)
    )
    for dimension, budget in ((2, 1000), (5, 2500)):
        defined.extend(
            _cell(
                "constant",
                f"{dimension}, {constant:g}",
                "rastrigin",
                dimension,
                budget,
                "box",
                n_subdivisions=10,
                configuration="pure_convexification",
                overrides={"convexification_constant": constant},
            )
            for constant in (10.0, 30.0, 50.0, 100.0, 200.0)
        )
    for label, kind, step in (
        ("unit, 2", "unit", 2),
        ("unit, 1", "unit", 1),
        ("none", "none", 1),
        ("proximity, 3", "proximity", 3),
    ):
        defined.extend(
            _cell("metric", label, name, 2, 1000, "metric", kind=kind, step=step)
            for name in ("rastrigin", "ackley", "griewank")
        )
    for radius in (1, 2, 3, 5):
        defined.extend(
            _cell(
                "radius",
                radius,
                name,
                5,
                2500,
                "box",
                n_subdivisions=10,
                overrides={"max_step": radius},
            )
            for name in four
        )
    for label, n_split, m in (
        ("all 5, 2", 5, 2),
        ("3, 4", 3, 4),
        ("2, 10", 2, 10),
        ("2, 5", 2, 5),
        ("1, 10", 1, 10),
    ):
        defined.append(
            _cell(
                "partial",
                label,
                "partly_multimodal",
                5,
                2500,
                "partial",
                n_split=n_split,
                n_subdivisions=m,
            )
        )
    three = ("rastrigin", "ackley", "styblinski_tang")
    for name in three:
        defined.extend(
            _cell("multires", f"flat, {m}", name, 5, 2500, "box", n_subdivisions=m)
            for m in (10, 16)
        )
        for branching, levels in ((2, 4), (2, 5), (4, 2), (4, 3)):
            defined.append(
                _cell(
                    "multires",
                    f"{branching}, {levels}",
                    name,
                    5,
                    2500,
                    "multires",
                    branching=branching,
                    levels=levels,
                )
            )
        defined.extend(
            _cell("hierarchies", f"flat, {m}", name, 5, 2500, "box", n_subdivisions=m)
            for m in (2, 10)
        )
        defined.extend((
            _cell("hierarchies", "two levels, value", name, 5, 2500, "two_level"),
            _cell(
                "hierarchies",
                "two levels, cuts",
                name,
                5,
                2500,
                "two_level",
                ranking="cuts",
            ),
            _cell("hierarchies", "deep", name, 5, 2500, "deep"),
            _cell("hierarchies", "frontier", name, 5, 2500, "frontier"),
        ))
    for budget in (2500, 5000, 10000):
        defined.extend((
            _cell(
                "budget",
                f"flat, {budget}",
                "ackley",
                5,
                budget,
                "box",
                n_subdivisions=10,
            ),
            _cell("budget", f"deep, {budget}", "ackley", 5, budget, "deep"),
        ))
    return defined


def _key(cell: dict, seed: int) -> str:
    """Return what identifies a run of a cell.

    Args:
        cell: The definition of the cell.
        seed: The seed of the starting point.

    Returns:
        The identifier.
    """
    return json.dumps([
        cell["table"],
        cell["row"],
        cell["problem"],
        cell["budget"],
        seed,
    ])


def _enumeration_start(seed: int):  # noqa: ANN202
    """Return the starting point of the enumeration harness.

    Args:
        seed: The seed of the starting point.

    Returns:
        The starting point.
    """
    from numpy.random import default_rng

    from benchmarks.problems import RASTRIGIN_LOWER_BOUND
    from benchmarks.problems import RASTRIGIN_UPPER_BOUND

    return default_rng(seed).uniform(RASTRIGIN_LOWER_BOUND, RASTRIGIN_UPPER_BOUND, 2)


def run(cell: dict, seed: int) -> dict[str, Any]:  # noqa: C901, PLR0911
    """Run one cell from one starting point.

    Args:
        cell: The definition of the cell.
        seed: The seed of the starting point.

    Returns:
        The distance to the optimum and the cost, with the number of boxes
        solved for the enumeration harness.
    """
    data_profiles._single_threaded()
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    problem = PROBLEMS[cell["problem"]]
    dimension, budget = cell["dimension"], cell["budget"]
    optimum = problem.optimum(dimension)
    settings = cell["settings"]
    runner = cell["runner"]
    if runner in {"enumeration", "oa"}:
        from benchmarks import test_outer_approximation_vs_enumeration as harness

        function = (
            harness._run_enumeration
            if runner == "enumeration"
            else harness._run_outer_approximation
        )
        best, boxes, executions = function(_enumeration_start(seed), "normalized")
        return {"gap": best, "cost": executions, "boxes": boxes}

    if runner == "box":
        from benchmarks.baselines import run_box_subdivision

        result = run_box_subdivision(problem, dimension, seed, budget, True, **settings)
        return {"gap": result.gap(optimum), "cost": result.cost_adjoint}

    if runner == "metric":
        from benchmarks import trust_region

        result = trust_region.run(
            problem, dimension, seed, budget, settings["kind"], 10, settings["step"]
        )
        return {"gap": result.gap(optimum), "cost": result.cost_adjoint}

    if runner == "sweep":
        from benchmarks import convexity_sweep

        result, _ = convexity_sweep.run(problem, seed, **settings)
        return {"gap": result.gap(optimum), "cost": result.cost_adjoint}

    if runner in {"density", "swept_density"}:
        from benchmarks import basin_spacing

        function = (
            basin_spacing.run_at_density
            if runner == "density"
            else basin_spacing.run_at_density_swept
        )
        outcome = function(problem, dimension, settings["density"], seed, budget)
        return {"gap": outcome.best - optimum, "cost": outcome.cost}

    if runner == "partial":
        from benchmarks import refine_some_variables

        best, cost = refine_some_variables.run(
            problem,
            dimension,
            settings["n_split"],
            settings["n_subdivisions"],
            seed,
            budget,
        )
    elif runner == "multires":
        from benchmarks import multiresolution

        best, cost = multiresolution.run(problem, dimension, seed, budget, **settings)
    else:
        from benchmarks import hierarchy

        best, cost = hierarchy.RUNNERS[runner](
            problem, dimension, seed, budget, **settings
        )
    return {"gap": best - optimum, "cost": cost}


def _task(arguments: tuple[dict, int]) -> tuple[str, dict]:
    """Run a cell from a starting point, in a worker process.

    Args:
        arguments: The definition of the cell and the seed.

    Returns:
        The identifier of the run and its outcome.
    """
    cell, seed = arguments
    try:
        outcome = run(cell, seed)
    except Exception as error:  # noqa: BLE001
        outcome = {"error": repr(error)}
    return _key(cell, seed), outcome


def _summary(cell: dict, outcomes: list[dict]) -> dict:
    """Return the summary of a cell over its starting points.

    Args:
        cell: The definition of the cell.
        outcomes: The outcome of each run.

    Returns:
        The median distance and cost, the number of runs reaching the optimum,
        stopped by the budget and failed.
    """
    done = [o for o in outcomes if "error" not in o]
    optimum = PROBLEMS[cell["problem"]].optimum(cell["dimension"])
    tolerance = data_profiles.TOLERANCE * max(1.0, abs(optimum))
    summary = {
        **{k: cell[k] for k in ("table", "row", "problem", "dimension", "budget")},
        "runs": len(outcomes),
        "failed": len(outcomes) - len(done),
    }
    if done:
        summary |= {
            "median_gap": median(o["gap"] for o in done),
            "median_cost": median(o["cost"] for o in done),
            "min_cost": min(o["cost"] for o in done),
            "max_cost": max(o["cost"] for o in done),
            "reached": sum(o["gap"] <= tolerance for o in done),
            "at_budget": sum(o["cost"] >= cell["budget"] > 0 for o in done),
        }
        if "boxes" in done[0]:
            summary |= {
                "min_boxes": min(o["boxes"] for o in done),
                "max_boxes": max(o["boxes"] for o in done),
            }
    return summary


def main(tables: list[str] | None = None) -> None:
    """Run every cell of the requested tables, then summarize all the cells run.

    Args:
        tables: The labels of the tables to run.
            If ``None``, read them from the command line, every table if none.
    """
    tables = sys.argv[1:] if tables is None else tables
    defined = [c for c in cells() if not tables or c["table"] in tables]
    done = {}
    if RUNS.is_file():
        for line in RUNS.read_text(encoding="utf-8").splitlines():
            key, outcome = json.loads(line)
            done[key] = outcome
    # The five-dimensional cells first, the slowest at the end of no queue.
    missing = sorted(
        ((c, s) for c in defined for s in SEEDS if _key(c, s) not in done),
        key=lambda task: -task[0]["dimension"] * max(task[0]["budget"], 1),
    )
    RUNS.parent.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(initializer=data_profiles._single_threaded) as executor:
        futures = [executor.submit(_task, task) for task in missing]
        for future in as_completed(futures):
            key, outcome = future.result()
            done[key] = outcome
            with RUNS.open("a", encoding="utf-8") as file:
                file.write(json.dumps([key, outcome]) + "\n")

    summaries = [
        _summary(c, [done[_key(c, s)] for s in SEEDS])
        for c in cells()
        if all(_key(c, s) in done for s in SEEDS)
    ]
    OUTPUT.write_text(
        json.dumps({"seeds": list(SEEDS), "cells": summaries}, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"{len(summaries)} cells summarized", flush=True)  # noqa: T201


if __name__ == "__main__":
    main()
