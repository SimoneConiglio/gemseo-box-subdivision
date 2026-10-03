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

"""Run a multistart of MMA on the SC 2D cantilever, its starts in parallel.

The first start is the preset's design; the others draw the pose of every bar,
its centre and its angle, uniformly within the bounds, and keep the preset's
length, thickness and density, as the sub-problems of the box subdivision are
restarted. Each start runs MMA with the preset's settings and the iteration cap
of a box. Run in the GGP environment, from the GGP repository:

    python <this repository>/benchmarks/cantilever/parallel_multistart.py \
        --preset short_cantilever_mna --starts 63 --processes 4 \
        --max-iter 1800 --out benchmarks/box_subdivision_mna

Each finished start is appended to ``<out>/multistart_<starts>.jsonl``, which a
run cut short resumes from.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path("benchmarks").resolve()))
import sc2d_box_subdivision as sc2d  # noqa: E402

POSE = (0, 1, 4)
"""The slots of a bar's pose: the centre and the angle."""


def starts(x_init: np.ndarray, number: int, seed: int) -> list[np.ndarray]:
    """Return the preset's design and random poses around its sizes."""
    rng = np.random.default_rng(seed)
    designs = [x_init.copy()]
    for _ in range(number - 1):
        x = x_init.copy()
        for slot in POSE:
            x[slot :: sc2d.VPC] = rng.uniform(0.0, 1.0, x[slot :: sc2d.VPC].size)
        designs.append(x)
    return designs


def solve(task: tuple[int, np.ndarray, str, int]) -> dict:
    """Run MMA from one start and return its best feasible design."""
    from gemseo import create_design_space
    from gemseo import create_scenario

    index, x0, preset, max_iter = task
    sc2d.select_preset(preset)
    spec = sc2d.load_spec()
    geometry, physics, _, _ = sc2d.build_disciplines(spec)
    history = sc2d._History(geometry, physics)
    design_space = create_design_space()
    design_space.add_variable(
        "x_vars", size=x0.size, lower_bound=0.0, upper_bound=1.0, value=x0
    )
    scenario = create_scenario(
        [geometry, physics],
        objective_name="compliance",
        design_space=design_space,
        formulation_name="MDF",
    )
    scenario.add_constraint("volume", constraint_type="ineq", positive=False, value=0.0)
    options = dict(spec.solver.options)
    options["algo_name"] = spec.solver.algorithm
    options["max_iter"] = max_iter
    start = time.time()
    scenario.execute(**options)
    try:
        compliance, x_best, _ = history.best()
    except RuntimeError:
        compliance, x_best = float("nan"), np.asarray(history.x[-1])
    return {
        "start": index,
        "compliance": compliance,
        "designs": history.unique,
        "solves": len(history),
        "time_s": time.time() - start,
        "x_best": np.asarray(x_best).tolist(),
    }


def main() -> None:
    """Run the starts not yet in the output file, then summarize them all."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", default="short_cantilever_mna")
    parser.add_argument("--starts", type=int, default=63)
    parser.add_argument("--processes", type=int, default=4)
    parser.add_argument("--max-iter", type=int, default=1800)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=Path("benchmarks/box_subdivision"))
    args = parser.parse_args()

    sc2d.select_preset(args.preset)
    _, _, x_init, _ = sc2d.build_disciplines(sc2d.load_spec())
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"multistart_{args.starts}.jsonl"
    done = (
        {json.loads(line)["start"] for line in path.read_text().splitlines()}
        if path.is_file()
        else set()
    )
    tasks = [
        (index, x, args.preset, args.max_iter)
        for index, x in enumerate(starts(x_init, args.starts, args.seed))
        if index not in done
    ]
    with Pool(args.processes) as pool:
        for result in pool.imap_unordered(solve, tasks):
            with path.open("a") as file:
                file.write(json.dumps(result) + "\n")
            print(
                f"start {result['start']:3d}: C = {np.expm1(result['compliance']):.2f}"
                f", {result['designs']} designs, {result['time_s']:.0f} s",
                flush=True,
            )

    results = [json.loads(line) for line in path.read_text().splitlines()]
    compliance = np.expm1([result["compliance"] for result in results])
    print(
        f"{len(results)} starts: best C = {np.nanmin(compliance):.2f}, median "
        f"{np.nanmedian(compliance):.2f}, {sum(r['designs'] for r in results)} designs"
    )


if __name__ == "__main__":
    main()
