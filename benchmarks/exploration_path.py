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
"""Draw the exploration of the swept method on the Rastrigin function, n = 2.

The configuration compared with the baselines, four probes and ten
subdivisions per variable, is run from one starting point, and every master
problem built during the run is recorded. For each of them, the outer
approximation, the largest of the cuts after the adaptive repair, and the trust
region are evaluated in every box from the constraints of the master problem
itself, so that the figure shows what the master problem solved:

- the boxes of the initial design of experiments, coloured by their value;
- for each probe of the second round, the prediction of the outer
  approximation in every box of its trust region and the box it selects;
- the boxes solved during the whole run, in the order of the rounds.

    python benchmarks/exploration_path.py --seed 0 \
        --out paper/figures/exploration.pdf
"""

from __future__ import annotations

import argparse
import json
import logging
import operator
from itertools import starmap
from pathlib import Path
from typing import Any

import numpy as np

N_SUBDIVISIONS = 10
"""The number of intervals per variable."""

DIMENSION = 2
"""The number of design variables."""

BUDGET = 1000
"""The budget in equivalent evaluations."""


def _box(alpha: np.ndarray) -> tuple[int, int]:
    """Return the interval indices of a one-hot vector.

    Args:
        alpha: The one-hot vector, the intervals of ``x_1`` first.

    Returns:
        The index of the interval of each variable.
    """
    blocks = np.asarray(alpha)[: DIMENSION * N_SUBDIVISIONS]
    return tuple(int(i) for i in np.argmax(blocks.reshape(DIMENSION, -1), axis=1))


def _one_hot(box: tuple[int, int]) -> np.ndarray:
    """Return the one-hot vector of a box.

    Args:
        box: The index of the interval of each variable.

    Returns:
        The one-hot vector.
    """
    alpha = np.zeros(DIMENSION * N_SUBDIVISIONS)
    for variable, index in enumerate(box):
        alpha[variable * N_SUBDIVISIONS + index] = 1.0
    return alpha


def _master(  # noqa: ANN401
    problem: Any, min_dfk: float, radius: float, history: list
) -> dict[str, Any]:
    """Return the outer approximation and the trust region of a master problem.

    The cuts are the constraints ``cut(alpha) - eta <= 0``; the others restrict
    the boxes, among them the trust region.

    Args:
        problem: The mixed-integer linear program.
        min_dfk: The convexity margin of the adaptive repair.
        radius: The radius of the trust region.
        history: The boxes solved and their values.

    Returns:
        The prediction and the admissibility of every box, the box selected and
        the boxes solved.
    """
    prediction = np.full((N_SUBDIVISIONS, N_SUBDIVISIONS), -np.inf)
    admitted = np.ones((N_SUBDIVISIONS, N_SUBDIVISIONS), dtype=bool)
    for i in range(N_SUBDIVISIONS):
        for j in range(N_SUBDIVISIONS):
            x = np.append(_one_hot((i, j)), 0.0)
            for constraint in problem.constraints:
                if constraint.f_type != "ineq":
                    continue
                value = float(np.max(np.atleast_1d(constraint.evaluate(x))))
                if constraint.name.startswith("objective outer approximation"):
                    prediction[i, j] = max(prediction[i, j], value)
                elif value > 1e-9:
                    admitted[i, j] = False
    solution = problem.solution
    return {
        "delta": float(min_dfk),
        "radius": float(radius),
        "prediction": prediction.tolist(),
        "admitted": admitted.tolist(),
        "selected": None if solution is None else _box(solution.x_opt),
        "solved": history,
    }


def record(seed: int) -> list[dict[str, Any]]:
    """Run the method and return its master problems.

    Args:
        seed: The seed of the starting point.

    Returns:
        The master problems, in the order they were solved.
    """
    from gemseo_bilevel_outer_approximation.algos.opt.core import (  # noqa: PLC0415
        outer_approximation_optimizer as core,
    )

    from benchmarks import baselines  # noqa: PLC0415
    from benchmarks.problems import PROBLEMS  # noqa: PLC0415

    built = []
    original = core.OuterApproximationOptimizer._build_milp_problem

    def build(self, slopes_hist, alpha_hist, fopt_hist, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        problem = original(self, slopes_hist, alpha_hist, fopt_hist, *args, **kwargs)
        pairs = zip(alpha_hist, fopt_hist, strict=False)
        history = [[*_box(a), float(f)] for a, f in pairs]
        radius = kwargs.get("current_step", args[-1] if args else None)
        built.append((problem, self.min_dfk, radius, history))
        return problem

    core.OuterApproximationOptimizer._build_milp_problem = build
    logging.disable(logging.CRITICAL)
    try:
        baselines.run_swept_box_subdivision(
            PROBLEMS["rastrigin"],
            DIMENSION,
            seed,
            BUDGET,
            True,
            n_subdivisions=N_SUBDIVISIONS,
        )
    finally:
        core.OuterApproximationOptimizer._build_milp_problem = original
    return list(starmap(_master, built))


def draw(masters: list[dict[str, Any]], path: Path) -> None:
    """Draw the initial boxes, the probes of the second round and the run.

    Args:
        masters: The master problems, in the order they were solved.
        path: The file of the figure.
    """
    import matplotlib.pyplot as plt  # noqa: PLC0415
    from matplotlib.patches import Rectangle  # noqa: PLC0415

    from benchmarks.problems import RASTRIGIN_LOWER_BOUND as LOW  # noqa: PLC0415
    from benchmarks.problems import rastrigin  # noqa: PLC0415

    width = 1.0
    initial = masters[0]["solved"]
    second = [m for m in masters if len(m["solved"]) == len(initial)]
    final = masters[-1]["solved"]
    incumbent = min(initial, key=operator.itemgetter(2))

    grid = np.linspace(LOW, LOW + N_SUBDIVISIONS * width, 201)
    xx, yy = np.meshgrid(grid, grid)
    values = np.vectorize(lambda a, b: rastrigin(np.array([a, b])))(xx, yy)

    def frame(axis, title: str) -> None:
        axis.contour(xx, yy, values, levels=8, colors="0.85", linewidths=0.3)
        axis.set_xlim(LOW, LOW + N_SUBDIVISIONS * width)
        axis.set_ylim(LOW, LOW + N_SUBDIVISIONS * width)
        axis.set_xticks(range(-4, 6, 2))
        axis.set_yticks(range(-4, 6, 2))
        axis.tick_params(labelsize=6)
        axis.set_aspect("equal")
        axis.set_title(title, fontsize=7)
        for k in range(N_SUBDIVISIONS + 1):
            axis.axhline(LOW + k * width, color="0.88", linewidth=0.3)
            axis.axvline(LOW + k * width, color="0.88", linewidth=0.3)

    def box(axis, i, j, **kwargs) -> None:
        corner = (LOW + i * width, LOW + j * width)
        axis.add_patch(Rectangle(corner, width, width, **kwargs))

    def outline(axis, i, j, color, linewidth=1.6) -> None:
        box(axis, i, j, fill=False, edgecolor=color, linewidth=linewidth, zorder=5)
        if color == "black":
            box(axis, i, j, fill=False, edgecolor="white", linewidth=0.6, zorder=5)

    cmap = plt.get_cmap("viridis")
    pmap = plt.get_cmap("magma")
    figure, axes = plt.subplots(2, 3, figsize=(7.2, 5.0), constrained_layout=True)
    axes = axes.ravel()

    # Initial design of experiments, coloured by the value of each box.
    low = min(b[2] for b in final)
    high = max(b[2] for b in final)
    norm = plt.Normalize(low, high)
    frame(axes[0], "initial boxes, value $v$")
    for i, j, value in initial:
        box(axes[0], i, j, facecolor=cmap(norm(value)), edgecolor="none", zorder=3)
    outline(axes[0], incumbent[0], incumbent[1], "black")
    figure.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=axes[0], shrink=0.7
    ).ax.tick_params(labelsize=6)

    # Probes of the second round: prediction in the trust region, box selected.
    for k, master in enumerate(second[:4], start=1):
        axis = axes[k]
        prediction = np.array(master["prediction"])
        admitted = np.array(master["admitted"])
        shown = prediction[admitted]
        pnorm = plt.Normalize(shown.min(), shown.max())
        frame(
            axis,
            f"probe {k}: $\\Delta = {master['radius']:.2g}$, "
            f"$\\delta = {master['delta']:.3g}$",
        )
        for i in range(N_SUBDIVISIONS):
            for j in range(N_SUBDIVISIONS):
                if admitted[i, j]:
                    box(
                        axis,
                        i,
                        j,
                        facecolor=pmap(pnorm(prediction[i, j])),
                        edgecolor="none",
                        zorder=3,
                    )
        for i, j, _ in initial:
            axis.plot(
                LOW + (i + 0.5) * width,
                LOW + (j + 0.5) * width,
                "o",
                color="white",
                markeredgecolor="black",
                markersize=3,
                zorder=6,
            )
        outline(axis, incumbent[0], incumbent[1], "black")
        if master["selected"] is not None:
            outline(axis, *master["selected"], "deepskyblue", 2.0)
        bar = figure.colorbar(
            plt.cm.ScalarMappable(norm=pnorm, cmap=pmap), ax=axis, shrink=0.7
        )
        bar.ax.tick_params(labelsize=6)
        bar.set_label("prediction", fontsize=6)

    # Whole run: boxes solved, coloured by value, numbered by round.
    axis = axes[5]
    frame(axis, "boxes solved during the run, value $v$")
    sizes = sorted({len(m["solved"]) for m in masters} | {len(final)})
    for index, (i, j, value) in enumerate(final):
        box(axis, i, j, facecolor=cmap(norm(value)), edgecolor="none", zorder=3)
        number = 1 + sum(size <= index for size in sizes)
        axis.text(
            LOW + (i + 0.5) * width,
            LOW + (j + 0.5) * width,
            str(number),
            ha="center",
            va="center",
            fontsize=5,
            zorder=6,
            color="black" if norm(value) > 0.6 else "white",
        )
    best = min(final, key=operator.itemgetter(2))
    outline(axis, best[0], best[1], "black")
    axis.plot(0.0, 0.0, "*", color="orange", markersize=8, zorder=7)
    figure.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=axis, shrink=0.7
    ).ax.tick_params(labelsize=6)

    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path)


def main() -> None:
    """Parse the command line, run and draw."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=Path("exploration.pdf"))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    masters = record(args.seed)
    if args.json:
        args.json.write_text(json.dumps(masters))
    draw(masters, args.out)


if __name__ == "__main__":
    main()
