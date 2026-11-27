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
r"""Run multistart MMA or monotonic basin hopping on the port of the cantilever.

Both use the problem, the MMA settings and the logs of
``port_box_subdivision.py``, so that their runs are compared with those of the
box subdivision at the same number of designs evaluated:

- ``multistart``: MMA from the reference initial design (repetition 0 only) and
  from random initial designs, whose bar positions and angles are drawn
  uniformly, until the budget is spent;
- ``basin_hopping``: monotonic basin hopping. MMA is run from the initial design;
  then, at each iteration, ``--processes`` perturbations of the incumbent are
  solved in parallel, each one moving one or two bar positions or angles, drawn
  at random, into another of the ``--n-subdivisions`` intervals of their range,
  as a box of the subdivision at a Hamming distance of one or two would, and MMA
  is run from it over the whole design space; the best result replaces the
  incumbent when it improves on it.

Repetition 0 starts from the reference initial design, the others from the
random initial design of ``--start-seed``::

    python benchmarks/cantilever/local_baselines.py basin_hopping \
        --backend ggp_mna_port.py --budget 30000 --start-seed 1 --out runs/mbh_1
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contextlib
import operator

from classic_tunneling import MMA_OPTIONS  # noqa: E402
from classic_tunneling import TOLERANCE  # noqa: E402
from classic_tunneling import mma  # noqa: E402
from port_box_subdivision import load_problem  # noqa: E402
from port_box_subdivision import pose_indices  # noqa: E402
from port_box_subdivision import random_start  # noqa: E402
from port_box_subdivision import summarize  # noqa: E402

WORKER: dict = {}
"""The problem and the counted evaluations of a worker process."""


class BudgetSpentError(RuntimeError):
    """The budget of designs is spent."""


def _init_worker(backend: str, out: str, total, budget: int, start: float) -> None:  # noqa: ANN001
    """Build the problem of a worker and its counted, logged evaluations."""
    problem = load_problem(backend)
    log = Path(out) / f"{os.getpid()}.bin"
    last: list = []

    def evaluate(x: np.ndarray) -> dict:
        x = np.clip(np.asarray(x, float), 0.0, 1.0)
        if last and np.array_equal(last[0], x):
            return last[1]
        with total.get_lock():
            if total.value >= budget:
                raise BudgetSpentError
            total.value += 1
        outputs = problem.physics(x)
        row = np.concatenate([
            [time.time() - start, outputs["compliance"], outputs["g"]],
            x,
        ])
        with log.open("ab") as file:
            row.astype(np.float64).tofile(file)
        last[:] = [x, outputs]
        return outputs

    WORKER.update(problem=problem, evaluate=evaluate)


def _local(task: tuple[np.ndarray, int]) -> tuple[np.ndarray | None, float]:
    """Run MMA from a design; return the best feasible design and its value."""
    start, max_iter = task
    visited = []
    with contextlib.suppress(BudgetSpentError):
        visited = mma(WORKER["evaluate"], start, dict(MMA_OPTIONS), max_iter)
    feasible = [(f, x) for x, f, g in visited if g <= TOLERANCE]
    if not feasible:
        return None, np.inf
    f, x = min(feasible, key=operator.itemgetter(0))
    return x, f


def _perturb(
    x: np.ndarray, rng: np.random.Generator, n_subdivisions: int
) -> np.ndarray:
    """Move one or two bar positions or angles into another interval."""
    y = np.array(x)
    poses = pose_indices(x.size)
    for index in rng.choice(poses, size=int(rng.integers(1, 3)), replace=False):
        current = min(int(y[index] * n_subdivisions), n_subdivisions - 1)
        other = rng.choice([k for k in range(n_subdivisions) if k != current])
        y[index] = (other + rng.uniform()) / n_subdivisions
    return y


def run(args: argparse.Namespace) -> dict:
    """Run the method to the budget and return its summary."""
    args.out.mkdir(parents=True, exist_ok=True)
    for path in args.out.glob("*.bin"):
        path.unlink()
    problem = load_problem(args.backend)
    start = (
        problem.x_init.copy()
        if args.start_seed is None
        else random_start(problem.x_init, args.start_seed)
    )
    rng = np.random.default_rng(1000 + (args.start_seed or 0))
    context = multiprocessing.get_context("fork")
    total = context.Value("q", 0)
    began = time.time()
    with context.Pool(
        args.processes,
        _init_worker,
        (args.backend, str(args.out), total, args.budget, began),
    ) as pool:
        if args.method == "multistart":

            def starts():  # noqa: ANN202
                yield start
                while True:
                    yield random_start(problem.x_init, int(rng.integers(2**31)))

            tasks = ((x, args.max_iter) for x in starts())
            for _ in pool.imap_unordered(_local, tasks):
                if total.value >= args.budget:
                    break
        else:
            incumbent, value = pool.apply(_local, ((start, args.max_iter),))
            if incumbent is None:
                incumbent, value = start, np.inf
            while total.value < args.budget:
                tasks = [
                    (_perturb(incumbent, rng, args.n_subdivisions), args.max_iter)
                    for _ in range(args.processes)
                ]
                for x, f in pool.map(_local, tasks):
                    if x is not None and f < value:
                        incumbent, value = x, f
        pool.terminate()

    summary = summarize(args.out, problem.x_init.size, args.budget)
    summary.update({
        "method": args.method,
        "start_seed": args.start_seed,
        "budget": args.budget,
        "wall_time_s": time.time() - began,
    })
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def main() -> None:
    """Parse the command line and run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("method", choices=("multistart", "basin_hopping"))
    parser.add_argument("--backend", required=True)
    parser.add_argument("--budget", type=int, default=30_000)
    parser.add_argument("--start-seed", type=int)
    parser.add_argument("--n-subdivisions", type=int, default=10)
    parser.add_argument("--max-iter", type=int, default=1800)
    parser.add_argument("--processes", type=int, default=4)
    parser.add_argument("--out", type=Path, required=True)
    summary = run(parser.parse_args())
    print(json.dumps({k: v for k, v in summary.items() if k != "x_best"}))  # noqa: T201


if __name__ == "__main__":
    main()
