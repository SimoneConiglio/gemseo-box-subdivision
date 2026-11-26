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

r"""Run the box subdivision on the short cantilever of a NumPy port of GGP_main.m.

The problem is that of ``trivial_start.py`` and ``sc2d_box_subdivision.py`` of
the GGP package, built here on a module defining a class ``Cantilever``, as for
``classic_tunneling.py --backend``: the pose of every bar, the coordinates of
its centre and its angle, is divided into ``--n-subdivisions`` intervals, the
length, the thickness and the density remain variables of each sub-problem,
the objective is :math:`\\log(C + 1)` and the volume constraint is declared at
the main level. The convexity is swept, each sub-problem is solved by MMA with
the settings of ``mmasub.m`` and at most ``--sub-max-iter`` iterations, and the
probes of the master are solved over ``--processes`` processes, which needs
merge request 139 of gemseo-bilevel-outer-approximation. ``--master-max-iter``
bounds the rounds of the master, of up to ``--probes`` boxes each; runs with
different numbers of probes are compared at the same number of designs analysed,
``--budget``, read off the logs, the run being stopped once past it.

It is used to compare numbers of probes on the same code, the GGP environment
with legacy FEniCS being unavailable; its results are not those of the GGP
implementation. Every evaluation is appended, by the process making it, to
``<out>/<pid>.bin``: the time, the compliance, the volume constraint and the
design, in float64. ``--summarize <out>`` reads these logs back, up to
``--budget`` distinct designs if given:

    python benchmarks/cantilever/port_box_subdivision.py \
        --backend ggp_mna_port.py --probes 16 --master-max-iter 64 \
        --processes 4 --out runs/probes_16
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classic_tunneling import MMA_OPTIONS  # noqa: E402
from classic_tunneling import TOLERANCE  # noqa: E402

VPC = 6
"""The variables of a bar: the centre, the length, the thickness, the angle and
the density."""

POSE = (0, 1, 4)
"""The slots of a bar that are subdivided: its centre and its angle."""

SPLIT = "x_split"
"""The subdivided variables."""

FREE = "x_free"
"""The variables of every sub-problem."""


def load_problem(backend: str):  # noqa: ANN201
    """Return the cantilever of a module defining ``Cantilever``.

    Args:
        backend: The path of the module.

    Returns:
        The problem.
    """
    spec = importlib.util.spec_from_file_location("cantilever_backend", backend)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Cantilever()


def create_discipline(problem, out: Path):  # noqa: ANN001, ANN201
    """Return the discipline of the cantilever, logging every evaluation.

    Args:
        problem: The cantilever.
        out: The directory of the logs.

    Returns:
        The discipline, of inputs ``x_split`` and ``x_free`` and of outputs the
        objective ``f``, the constraint ``g`` and the compliance.
    """
    from gemseo.core.discipline.discipline import Discipline  # noqa: PLC0415

    size = problem.x_init.size
    split = np.array([c * VPC + s for c in range(size // VPC) for s in POSE])
    free = np.setdiff1d(np.arange(size), split)
    start = time.time()

    class Cantilever(Discipline):
        """The cantilever, its value and gradients from one analysis."""

        def __init__(self) -> None:
            super().__init__(name="Cantilever")
            self.input_grammar.update_from_names([SPLIT, FREE])
            self.output_grammar.update_from_names(["f", "g", "compliance"])
            self.default_input_data = {
                SPLIT: problem.x_init[split].copy(),
                FREE: problem.x_init[free].copy(),
            }
            self.__last: tuple[bytes, dict] | None = None

        def _outputs(self) -> dict:
            x = np.empty(size)
            x[split] = np.ravel(self.io.data[SPLIT])
            x[free] = np.ravel(self.io.data[FREE])
            key = x.tobytes()
            if self.__last is None or self.__last[0] != key:
                outputs = problem.physics(x)
                row = np.concatenate([
                    [time.time() - start, outputs["compliance"], outputs["g"]],
                    x,
                ])
                with (out / f"{os.getpid()}.bin").open("ab") as file:
                    row.astype(np.float64).tofile(file)
                self.__last = (key, outputs)
            return self.__last[1]

        def _run(self, input_data):  # noqa: ANN001, ANN202
            outputs = self._outputs()
            return {
                "f": np.array([outputs["f"]]),
                "g": np.array([outputs["g"]]),
                "compliance": np.array([outputs["compliance"]]),
            }

        def _compute_jacobian(self, input_names=(), output_names=()) -> None:  # noqa: ARG002
            outputs = self._outputs()
            self.jac = {
                name: {
                    SPLIT: np.atleast_2d(outputs[gradient][split]),
                    FREE: np.atleast_2d(outputs[gradient][free]),
                }
                for name, gradient in (("f", "df"), ("g", "dg"))
            }
            self.jac["compliance"] = {
                variable: self.jac["f"][variable] * (outputs["compliance"] + 1)
                for variable in (SPLIT, FREE)
            }

    return Cantilever(), split, free


def run(args: argparse.Namespace) -> None:
    """Run the box subdivision and write its summary.

    Args:
        args: The arguments of the command line.
    """
    from gemseo import create_design_space  # noqa: PLC0415

    from gemseo_box_subdivision import BoxSubdivisionScenario  # noqa: PLC0415
    from gemseo_box_subdivision import SweptBoxSubdivisionSettings  # noqa: PLC0415

    args.out.mkdir(parents=True, exist_ok=True)
    problem = load_problem(args.backend)
    discipline, split, free = create_discipline(problem, args.out)
    design_space = create_design_space()
    for name, indices in ((SPLIT, split), (FREE, free)):
        design_space.add_variable(
            name,
            size=indices.size,
            lower_bound=0.0,
            upper_bound=1.0,
            value=problem.x_init[indices],
        )

    original = SweptBoxSubdivisionSettings.to_master_settings

    def to_master_settings(self, radius=None):  # noqa: ANN001, ANN202
        """Return the settings of the master, its probes spread over processes."""
        return {**original(self, radius), "number_of_processes": args.processes}

    SweptBoxSubdivisionSettings.to_master_settings = to_master_settings
    settings = SweptBoxSubdivisionSettings(
        n_parallel_points=args.probes,
        max_iter=args.master_max_iter,
        trust_region_radius=args.trust_region_radius,
        sub_problem_max_iter=args.sub_max_iter,
        sub_problem_algo_name="MMA",
        sub_problem_algo_settings=dict(MMA_OPTIONS),
    )
    scenario = BoxSubdivisionScenario(
        [discipline],
        "f",
        design_space,
        n_subdivisions={SPLIT: args.n_subdivisions},
        formulation="normalized",
        settings=settings,
    )
    scenario.formulation.add_constraint(
        "g", constraint_type="ineq", value=0.0, main_level=True
    )
    start = time.time()
    scenario.execute()
    elapsed = time.time() - start
    summary = summarize(args.out, problem.x_init.size)
    summary.update({
        "probes": args.probes,
        "master_max_iter": args.master_max_iter,
        "n_subdivisions": args.n_subdivisions,
        "sub_max_iter": args.sub_max_iter,
        "trust_region_radius": args.trust_region_radius,
        "processes": args.processes,
        "wall_time_s": elapsed,
    })
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "boxes"}, indent=1))


def summarize(out: Path, size: int, budget: int | None = None) -> dict:
    """Return the best feasible compliance and the designs of a run.

    The boxes are read off the logs: in the normalized formulation a sub-problem
    starts at the centre of its box, so that a new box begins where the
    subdivided poses jump, which is not checked here; the boxes are counted by
    the master instead.

    Args:
        out: The directory of the logs.
        size: The number of design variables.
        budget: The number of distinct designs, in the order of time, beyond
            which the logs are ignored; ``None`` to read them all.

    Returns:
        The best feasible compliance, the number of distinct designs analysed in
        all, the number analysed until the best, in the order of time, the time
        to the best and the best design.
    """
    rows = np.concatenate([
        np.fromfile(path, dtype=np.float64).reshape(-1, 3 + size)
        for path in sorted(out.glob("*.bin"))
    ])
    rows = rows[np.argsort(rows[:, 0], kind="stable")]
    _, first = np.unique(rows[:, 3:].round(12), axis=0, return_index=True)
    rows = rows[np.sort(first)][:budget]
    feasible = rows[:, 2] <= TOLERANCE
    compliance = np.where(feasible, rows[:, 1], np.inf)
    best = int(np.argmin(compliance))
    return {
        "best_compliance": float(compliance[best]),
        "designs": len(rows),
        "designs_to_best": best + 1,
        "time_to_best_s": float(rows[best, 0]),
        "x_best": rows[best, 3:].tolist(),
    }


def main() -> None:
    """Parse the command line and run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--probes", type=int, default=9)
    parser.add_argument("--master-max-iter", type=int, default=64)
    parser.add_argument("--n-subdivisions", type=int, default=10)
    parser.add_argument("--sub-max-iter", type=int, default=1800)
    parser.add_argument("--trust-region-radius", type=int, default=2)
    parser.add_argument("--processes", type=int, default=4)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--budget", type=int)
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    if args.summarize:
        size = load_problem(args.backend).x_init.size
        summary = summarize(args.out, size, args.budget)
        summary.pop("x_best")
        print(json.dumps(summary, indent=1))
    else:
        run(args)


if __name__ == "__main__":
    main()
